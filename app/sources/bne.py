"""Conector oficial para la Bolsa Nacional de Empleo de Chile (https://www.bne.cl/).

BNE es el portal público estatal administrado por SENCE / Ministerio del Trabajo.
Permite consultas sobre vacantes públicas respetando los términos de servicio mediante su API JSON.
"""

from __future__ import annotations

import html
import json
import logging
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp

from app.jobs.deduplication import compute_job_fingerprint
from app.jobs.models import JobPayload
from app.jobs.normalizer import normalize_job_payload
from app.sources.base import BaseJobSource, SourceError

logger = logging.getLogger(__name__)


class BNESource(BaseJobSource):
    """Conector para Bolsa Nacional de Empleo (BNE) mediante API JSON pública."""

    def __init__(self, poll_interval_minutes: int = 20) -> None:
        super().__init__(
            name="BNE",
            base_url="https://www.bne.cl",
            source_type="public_api",
            poll_interval_minutes=poll_interval_minutes,
            requires_auth=False,
            timeout_seconds=30,
            max_retries=3,
            rate_limit_delay=1.5,
        )
        # Endpoint observado en la busqueda publica oficial (noviembre de 2026).
        self.base_url = "https://bne.gob.cl"
        self.api_url = f"{self.base_url}/api/ofertas/busqueda"
        self.search_configs: list[dict[str, Any]] = [
            {"idsRegion": [391], "idsComuna": [1283, 1303]},
            {"textoBusqueda": "remoto"},
            {"textoBusqueda": "teletrabajo"},
        ]
        self.recovery_days = 4
        self.max_pages = 5
        self.access_notes = "Busqueda publica del portal BNE, sin autenticacion."

    async def fetch_jobs(
        self,
        session: aiohttp.ClientSession,
        criteria: Any | None = None,
    ) -> list[JobPayload]:
        """Consulta ofertas públicas en BNE para Informática y Región de Ñuble / Biobío."""
        all_jobs: list[JobPayload] = []
        seen_codes: set[str] = set()
        successful_requests = 0

        errors: list[str] = []
        cutoff = (datetime.now(ZoneInfo("America/Santiago")) - timedelta(days=self.recovery_days)).date()
        for config in self.search_configs:
            try:
                for page in range(self.max_pages):
                    text_response = await self.request_search_post(
                        session, self.api_url,
                        payload={"fechaPublicacion": cutoff.isoformat(), **config},
                        params={"page": page, "size": 50},
                    )
                    data = json.loads(text_response)
                    if not isinstance(data.get("content"), list):
                        raise SourceError("BNE cambio el formato de la busqueda publica")
                    successful_requests += 1
                    for item in data["content"]:
                        codigo = str(item.get("codigoOferta") or item.get("codigo") or item.get("id") or "")
                        if not codigo or codigo in seen_codes:
                            continue
                        seen_codes.add(codigo)
                        parsed_job = self._parse_bne_item(item)
                        if parsed_job:
                            all_jobs.append(parsed_job)
                    if page + 1 >= int(data.get("totalPages", 1)):
                        break
                    if page + 1 == self.max_pages:
                        logger.warning("BNE alcanzo el limite de %d paginas; consulta parcial", self.max_pages)
            except Exception as exc:
                errors.append(str(exc))
                logger.warning("[%s] Error consultando config %s: %s", self.name, config, exc)

        if not successful_requests:
            error = "BNE: ninguna consulta pudo completarse; el conector de busqueda requiere actualizacion."
            self.record_error(error)
            raise SourceError(error)
        if errors:
            self.record_error("Consulta parcial: " + errors[0])
        else:
            self.record_success(len(all_jobs))

        return all_jobs

    def _parse_bne_item(self, item: dict[str, Any]) -> JobPayload | None:
        """Convierte un objeto de oferta de BNE en JobPayload normalizado."""
        try:
            codigo = str(item.get("codigoOferta") or item.get("codigo") or item.get("id"))
            raw_title = item.get("nombrePuesto") or item.get("titulo") or "Oferta laboral"
            title = html.unescape(raw_title).strip()
            if not title or len(title) < 3:
                return None

            raw_company = (item.get("empresario") or {}).get("nombreComercial") or item.get("empresa") or "BNE Empleador"
            company = html.unescape(raw_company).strip()

            raw_desc = item.get("descripcion") or ""
            desc = html.unescape(raw_desc).strip()

            comuna = item.get("comuna")
            region = item.get("region")
            if isinstance(comuna, dict):
                comuna = comuna.get("nombre")
            if isinstance(region, dict):
                region = region.get("nombre")
            if comuna:
                comuna = html.unescape(comuna).strip()
            if region:
                region = html.unescape(region).strip()

            location_parts = [p for p in [comuna, region] if p]
            location = ", ".join(location_parts) if location_parts else "Chile"

            # Parsear fecha: formato común '16/10/26' o '16/10/2026'
            fecha_str = str(item.get("fechaPublicacion") or item.get("fecha") or "").strip()
            published_at = None
            if fecha_str:
                for fmt in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d"):
                    try:
                        published_at = datetime.strptime(fecha_str, fmt)
                        break
                    except ValueError:
                        continue

            # The public code (2026-...) is NOT the numeric detail-page ID.
            offer_id = str(item.get("id") or "")
            if not offer_id.isdecimal() or int(offer_id) <= 0:
                return None
            job_url = f"{self.base_url}/ofertas/{offer_id}"

            raw_payload = {
                "title": title,
                "url": job_url,
                "company": company,
                "location": location,
                "description": desc,
                "salary": (item.get("rangoSalarial") or {}).get("nombre"),
                "schedule": (item.get("jornadaLaboral") or {}).get("nombre"),
                "published_at": published_at,
                "region": region,
                "comuna": comuna,
                "external_id": codigo,
                "raw_data": {
                    "source": "BNE",
                    "codigo": codigo,
                    "id": item.get("id"),
                    "idEmpresa": item.get("idEmpresa"),
                    "origen": item.get("origen"),
                },
            }

            normalized = normalize_job_payload(raw_payload, source_name=self.name)
            compute_job_fingerprint(normalized)
            return normalized

        except Exception as err:
            logger.debug("[%s] Error parseando item BNE: %s", self.name, err)
            return None
