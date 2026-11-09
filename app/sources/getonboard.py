"""Conector a la API publica oficial de Get on Board."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

import aiohttp

from app.jobs.deduplication import compute_job_fingerprint
from app.jobs.models import JobPayload
from app.jobs.normalizer import clean_html, normalize_job_payload
from app.sources.base import BaseJobSource, SourceError

logger = logging.getLogger(__name__)


class GetOnBoardSource(BaseJobSource):
    def __init__(self) -> None:
        super().__init__(
            name="Get on Board", base_url="https://www.getonbrd.com",
            source_type="public_api", poll_interval_minutes=2, rate_limit_delay=1.0,
        )
        self.max_pages = 5
        self.access_notes = "API publica oficial, sin autenticacion; maximo 5 paginas por busqueda."

    async def fetch_jobs(
        self, session: aiohttp.ClientSession, criteria: Any | None = None
    ) -> list[JobPayload]:
        records_by_id: dict[str, dict[str, Any]] = {}
        errors: list[str] = []
        successful = 0
        for query in ("software", "data", "soporte", "remoto"):
            try:
                for page in range(1, self.max_pages + 1):
                    content = await self.request_get(
                        session, f"{self.base_url}/api/v0/search/jobs",
                        headers={"Accept": "application/json"},
                        params={"query": query, "page": page, "per_page": 120,
                                "expand[]": ["company", "location_cities"]},
                    )
                    data = json.loads(content)
                    if not isinstance(data.get("data"), list):
                        raise SourceError("Get on Board cambio el formato de respuesta")
                    successful += 1
                    for record in data["data"]:
                        if record.get("id"):
                            records_by_id[str(record["id"])] = record
                    if page >= int(data.get("meta", {}).get("total_pages", 1)):
                        break
                    if page == self.max_pages:
                        logger.warning("Get on Board: limite de paginas alcanzado para %s", query)
            except Exception as exc:
                errors.append(str(exc))
        if not successful:
            error = errors[0] if errors else "No se pudo consultar Get on Board"
            self.record_error(error)
            raise SourceError(error)
        jobs = []
        for record in records_by_id.values():
            try:
                payload = self._parse_record(record)
                if payload:
                    jobs.append(payload)
            except (ValueError, TypeError, KeyError) as exc:
                logger.warning("Get on Board: oferta invalida %s: %s", record.get("id"), exc)
        if errors:
            self.record_error("Consulta parcial: " + errors[0])
        else:
            self.record_success(len(jobs))
        return jobs

    def _parse_record(self, record: dict[str, Any]) -> JobPayload | None:
        attrs = record.get("attributes", {})
        job_id = str(record.get("id", ""))
        if not job_id or not attrs.get("title"):
            return None
        countries = [str(country) for country in (attrs.get("countries") or [])]
        # "Remoto" es la etiqueta de la API para ofertas sin pais fisico.
        # Las restricciones de residencia del texto se comprueban en el routing.
        if attrs.get("remote") and countries and not any(
            country.casefold() in {"remote", "remoto", "chile", "cl", "latam", "worldwide"}
            for country in countries
        ):
            return None
        description = "\n\n".join(
            clean_html(attrs.get(key))
            for key in ("description", "functions", "desirable", "projects", "benefits")
            if attrs.get(key)
        )
        cities = (attrs.get("location_cities") or {}).get("data", [])
        location = ", ".join(
            [(x.get("attributes") or {}).get("name") or str(x.get("id", "")) for x in cities]
            + countries
        )
        company = (((attrs.get("company") or {}).get("data") or {}).get("attributes") or {}).get("name")
        published = attrs.get("published_at")
        published_at = datetime.fromtimestamp(float(published), tz=UTC) if published else None
        remote_modality = attrs.get("remote_modality")
        modality = "hibrido" if remote_modality in {"hybrid", "partially_remote"} else (
            "remoto" if attrs.get("remote") else "presencial"
        )
        raw = {
            "external_id": job_id, "title": attrs["title"], "company": company or "",
            "description": description, "requirements": clean_html(attrs.get("description")),
            "location": location or ("Remoto" if attrs.get("remote") else "Chile"),
            "modality": modality,
            # La API expresa salarios en USD. El modelo local usa CLP: no convertir
            # ni presentar estos importes como pesos chilenos sin tasa verificada.
            "published_at": published_at,
            "url": (record.get("links") or {}).get("public_url") or f"{self.base_url}/jobs/{job_id}",
            "countries": countries, "remote_zone": attrs.get("remote_zone"),
            "source_attributes": attrs,
        }
        payload = normalize_job_payload(raw, source_name=self.name)
        # El normalizador infiere sueldos en CLP del texto: aqui no es apropiado.
        payload.salary_min = payload.salary_max = None
        payload.salary_type = None
        compute_job_fingerprint(payload)
        return payload
