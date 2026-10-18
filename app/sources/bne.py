"""Conector oficial para la Bolsa Nacional de Empleo de Chile (https://www.bne.cl/).

BNE es el portal público estatal administrado por SENCE / Ministerio del Trabajo.
Permite consultas sobre vacantes públicas respetando los términos de servicio mediante su API JSON.
"""

from __future__ import annotations

import html
import json
import logging
from datetime import datetime
from typing import Any

import aiohttp

from app.jobs.deduplication import compute_job_fingerprint
from app.jobs.models import JobPayload
from app.jobs.normalizer import normalize_job_payload
from app.sources.base import BaseJobSource

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
        self.api_url = "https://www.bne.cl/data/ofertas/buscarListas"
        # Búsquedas estratégicas:
        # idRegion=391: Ñuble (Chillán, San Carlos, etc.)
        # idRegion=384: Biobío (Concepción, etc.)
        # textoLibre=informatica / desarrollador: Informática nacional y remoto
        self.search_configs: list[dict[str, Any]] = [
            # 1. Región de Ñuble (Retail, comercio, operarios, bodega, etc.)
            {"idRegion": 391, "numResultadosPorPagina": 50},
            # 2. Informática a nivel nacional y remoto
            {"textoLibre": "informatica", "numResultadosPorPagina": 50},
            # 3. Desarrollador / Software a nivel nacional
            {"textoLibre": "desarrollador", "numResultadosPorPagina": 50},
            # 4. Región del Biobío (Concepción e Informática local)
            {"idRegion": 384, "textoLibre": "informatica", "numResultadosPorPagina": 30},
        ]

    async def fetch_jobs(
        self,
        session: aiohttp.ClientSession,
        criteria: Any | None = None,
    ) -> list[JobPayload]:
        """Consulta ofertas públicas en BNE para Informática y Región de Ñuble / Biobío."""
        all_jobs: list[JobPayload] = []
        seen_codes: set[str] = set()

        for config in self.search_configs:
            params: dict[str, Any] = {
                "mostrar": "empleo",
                "numPaginaRecuperar": 1,
                "clasificarYPaginar": "true",
                **config,
            }
            try:
                text_response = await self.request_get(session, self.api_url, params=params)
                data = json.loads(text_response)
                resultados = data.get("paginaOfertas", {}).get("resultados", [])

                for item in resultados:
                    codigo = str(item.get("codigo") or item.get("id") or "")
                    if not codigo or codigo in seen_codes:
                        continue
                    seen_codes.add(codigo)

                    parsed_job = self._parse_bne_item(item)
                    if parsed_job:
                        all_jobs.append(parsed_job)

            except Exception as e:
                logger.warning("[%s] Error consultando config %s: %s", self.name, config, e)

        if all_jobs:
            self.record_success(len(all_jobs))
        else:
            self.record_success(0)

        return all_jobs

    def _parse_bne_item(self, item: dict[str, Any]) -> JobPayload | None:
        """Convierte un objeto de oferta de BNE en JobPayload normalizado."""
        try:
            codigo = str(item.get("codigo") or item.get("id"))
            raw_title = item.get("titulo") or "Oferta laboral"
            title = html.unescape(raw_title).strip()
            if not title or len(title) < 3:
                return None

            raw_company = item.get("empresa") or "BNE Empleador"
            company = html.unescape(raw_company).strip()

            raw_desc = item.get("descripcion") or ""
            desc = html.unescape(raw_desc).strip()

            comuna = item.get("comuna")
            region = item.get("region")
            if comuna:
                comuna = html.unescape(comuna).strip()
            if region:
                region = html.unescape(region).strip()

            location_parts = [p for p in [comuna, region] if p]
            location = ", ".join(location_parts) if location_parts else "Chile"

            # Parsear fecha: formato común '16/10/26' o '16/10/2026'
            fecha_str = str(item.get("fecha") or "").strip()
            published_at = None
            if fecha_str:
                for fmt in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d"):
                    try:
                        published_at = datetime.strptime(fecha_str, fmt)
                        break
                    except ValueError:
                        continue

            job_url = f"https://www.bne.cl/oferta/{codigo}"

            raw_payload = {
                "title": title,
                "url": job_url,
                "company": company,
                "location": location,
                "description": desc,
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
