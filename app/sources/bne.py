"""Conector para la Bolsa Nacional de Empleo de Chile (https://www.bne.gob.cl/).

BNE es el portal público estatal administrado por SENCE / Ministerio del Trabajo.
Permite consultas sobre vacantes públicas respetando los términos de servicio.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

from app.jobs.deduplication import compute_job_fingerprint
from app.jobs.models import JobPayload
from app.jobs.normalizer import normalize_job_payload
from app.sources.base import BaseJobSource

logger = logging.getLogger(__name__)


class BNESource(BaseJobSource):
    """Conector para Bolsa Nacional de Empleo (BNE)."""

    def __init__(self, poll_interval_minutes: int = 30) -> None:
        super().__init__(
            name="BNE",
            base_url="https://www.bne.gob.cl",
            source_type="public_web",
            poll_interval_minutes=poll_interval_minutes,
            requires_auth=False,
            timeout_seconds=30,
            max_retries=2,
            rate_limit_delay=2.0,
        )
        self.search_url = "https://www.bne.gob.cl/ofertas-empleo"

    async def fetch_jobs(
        self,
        session: aiohttp.ClientSession,
        criteria: Any | None = None,
    ) -> list[JobPayload]:
        """Consulta ofertas públicas en BNE para el área de informática o Región de Ñuble."""
        jobs: list[JobPayload] = []

        params = {
            "region": "16",  # Región de Ñuble
            "texto": "informatica",
        }

        try:
            html = await self.request_get(session, self.search_url, params=params)
            jobs = self._parse_html(html)
            self.record_success(len(jobs))
        except Exception as e:
            logger.warning("[%s] Consulta a BNE no disponible o restringida: %s", self.name, e)
            self.record_error(str(e))

        return jobs

    def _parse_html(self, html: str) -> list[JobPayload]:
        """Parsea listados públicos de ofertas en el HTML de BNE."""
        soup = BeautifulSoup(html, "html.parser")
        job_cards = soup.find_all(
            ["div", "article"], class_=lambda c: c and ("card" in c or "oferta" in c or "job" in c)
        )

        results: list[JobPayload] = []
        for card in job_cards:
            try:
                title_elem = card.find(
                    ["h2", "h3", "h4", "a"], class_=lambda c: c and "title" in c
                ) or card.find("a")
                if not title_elem:
                    continue

                title = title_elem.get_text().strip()
                link = title_elem.get("href", "")
                if link and not link.startswith("http"):
                    link = f"https://www.bne.gob.cl{link}"

                if not title or len(title) < 4:
                    continue

                # Extraer empresa y ubicación
                company_elem = card.find(class_=lambda c: c and ("empresa" in c or "company" in c))
                company = company_elem.get_text().strip() if company_elem else "BNE Empleador"

                location_elem = card.find(
                    class_=lambda c: c and ("ubicacion" in c or "location" in c or "region" in c)
                )
                location = location_elem.get_text().strip() if location_elem else "Región de Ñuble"

                raw = {
                    "title": title,
                    "url": link or self.search_url,
                    "company": company,
                    "location": location,
                    "description": card.get_text(separator=" ").strip(),
                }

                payload = normalize_job_payload(raw, source_name=self.name)
                compute_job_fingerprint(payload)
                results.append(payload)
            except Exception as e:
                logger.debug("[%s] Error parseando tarjeta BNE: %s", self.name, e)
                continue

        return results
