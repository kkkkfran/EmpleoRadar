"""Conector para Emplea INACAP (https://emplea.inacap.cl / Emplea X Chile).

Portal oficial de empleabilidad de INACAP que conecta estudiantes, titulados y profesionales
con vacantes laborales públicas en todo Chile.
"""

from __future__ import annotations

import html
import json
import logging
import re
from datetime import datetime
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

from app.jobs.deduplication import compute_job_fingerprint
from app.jobs.models import JobPayload
from app.jobs.normalizer import normalize_job_payload
from app.sources.base import BaseJobSource

logger = logging.getLogger(__name__)


class InacapSource(BaseJobSource):
    """Conector para la bolsa de trabajo Emplea INACAP / Emplea X Chile."""

    def __init__(self, poll_interval_minutes: int = 25) -> None:
        super().__init__(
            name="EmpleaINACAP",
            base_url="https://emplea.inacap.cl",
            source_type="public_web",
            poll_interval_minutes=poll_interval_minutes,
            requires_auth=False,
            timeout_seconds=30,
            max_retries=3,
            rate_limit_delay=1.5,
        )
        self.search_url = "https://emplea.inacap.cl/trabajo/trabajos-en-chile"
        # Búsquedas estratégicas:
        # Search[region]=4235: Región de Ñuble (Chillán y comunas)
        # Search[region]=9: Región del Biobío (Concepción)
        # Search[terms]=informatica / desarrollador: Perfiles TI
        self.search_queries: list[dict[str, str]] = [
            # 1. Informática en todo Chile (más vacantes remotas)
            {"Search[terms]": "informatica", "Search[orderFilter]": ""},
            # 2. Desarrollador / Software
            {"Search[terms]": "desarrollador", "Search[orderFilter]": ""},
            # 3. Todas las vacantes en Región de Ñuble (Chillán)
            {"Search[region]": "4235", "Search[orderFilter]": ""},
            # 4. Todas las vacantes en Región del Biobío (Concepción)
            {"Search[region]": "9", "Search[orderFilter]": ""},
        ]

    async def fetch_jobs(
        self,
        session: aiohttp.ClientSession,
        criteria: Any | None = None,
    ) -> list[JobPayload]:
        """Consulta ofertas en Emplea INACAP estructuradas en Schema.org JSON-LD."""
        all_jobs: list[JobPayload] = []
        seen_urls: set[str] = set()

        for q_params in self.search_queries:
            try:
                html_text = await self.request_get(session, self.search_url, params=q_params)
                jobs = self._parse_inacap_page(html_text)

                for job in jobs:
                    if job.url not in seen_urls:
                        seen_urls.add(job.url)
                        all_jobs.append(job)

            except Exception as e:
                logger.warning("[%s] Error consultando query %s: %s", self.name, q_params, e)

        if all_jobs:
            self.record_success(len(all_jobs))
        else:
            self.record_success(0)

        return all_jobs

    def _parse_inacap_page(self, html_text: str) -> list[JobPayload]:
        """Parsea los datos estructurados Schema.org JSON-LD o tarjetas HTML de INACAP."""
        results: list[JobPayload] = []
        soup = BeautifulSoup(html_text, "html.parser")

        # 1. Intentar extracción por Schema.org JSON-LD (más precisa y estructurada)
        for s in soup.find_all("script", type="application/ld+json"):
            if not s.string:
                continue
            try:
                data = json.loads(s.string)
                main_entity = data.get("mainEntity") if isinstance(data, dict) else None
                if not main_entity or not isinstance(main_entity, dict):
                    continue

                items = main_entity.get("itemListElement", [])
                for list_item in items:
                    job_data = list_item.get("item") if isinstance(list_item, dict) else None
                    if not job_data or not isinstance(job_data, dict):
                        continue

                    parsed = self._parse_jsonld_job(job_data)
                    if parsed:
                        results.append(parsed)

            except Exception as json_err:
                logger.debug("[%s] Error parseando JSON-LD: %s", self.name, json_err)

        if results:
            return results

        # 2. Fallback: parsear enlaces tradicionales en la página
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/jobs/" in href or "/oferta-de-trabajo/" in href:
                title = a.get_text().strip()
                if not title or len(title) < 4:
                    continue
                full_url = href if href.startswith("http") else f"https://emplea.inacap.cl{href}"
                raw_payload = {
                    "title": title,
                    "url": full_url,
                    "company": "Empresa INACAP",
                    "location": "Chile",
                    "description": "",
                    "raw_data": {"source": "EmpleaINACAP", "url": full_url},
                }
                normalized = normalize_job_payload(raw_payload, source_name=self.name)
                compute_job_fingerprint(normalized)
                results.append(normalized)

        return results

    def _parse_jsonld_job(self, item: dict[str, Any]) -> JobPayload | None:
        """Convierte una entidad JobPosting de Schema.org en JobPayload."""
        try:
            raw_title = item.get("title") or ""
            title = html.unescape(raw_title).strip()
            if not title or len(title) < 3:
                return None

            job_url = str(item.get("url") or "").strip()
            if not job_url:
                return None

            # Extraer ID externo numérico de la URL (terminado en /12345 o -12345)
            ext_id_match = re.search(r"[/-](\d+)$", job_url)
            external_id = ext_id_match.group(1) if ext_id_match else job_url

            org_data = item.get("hiringOrganization") or {}
            raw_company = org_data.get("name") if isinstance(org_data, dict) else "Empresa INACAP"
            company = html.unescape(raw_company or "Empresa INACAP").strip()

            loc_data = item.get("jobLocation") or {}
            raw_loc = loc_data.get("address") if isinstance(loc_data, dict) else ""
            location_raw = html.unescape(raw_loc or "").strip()

            date_str = str(item.get("datePosted") or "").strip()
            published_at = None
            if date_str:
                for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y"):
                    try:
                        published_at = datetime.strptime(date_str[:10], fmt)
                        break
                    except ValueError:
                        continue

            raw_desc = item.get("description") or ""
            desc = html.unescape(raw_desc).strip()

            raw_payload = {
                "title": title,
                "url": job_url,
                "company": company,
                "location": location_raw,
                "description": desc,
                "published_at": published_at,
                "external_id": external_id,
                "raw_data": {
                    "source": "EmpleaINACAP",
                    "url": job_url,
                    "external_id": external_id,
                    "schema_org": item,
                },
            }

            normalized = normalize_job_payload(raw_payload, source_name=self.name)
            compute_job_fingerprint(normalized)
            return normalized

        except Exception as e:
            logger.debug("[%s] Error parseando oferta JSON-LD: %s", self.name, e)
            return None
