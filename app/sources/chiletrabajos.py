"""Conector oficial para ChileTrabajos (https://www.chiletrabajos.cl/).

Utiliza los feeds RSS públicos y páginas de búsqueda regional autorizadas.
"""

from __future__ import annotations

import logging
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

from app.jobs.deduplication import compute_job_fingerprint
from app.jobs.models import JobPayload
from app.jobs.normalizer import normalize_job_payload
from app.sources.base import BaseJobSource

logger = logging.getLogger(__name__)


class ChileTrabajosSource(BaseJobSource):
    """Conector para ChileTrabajos mediante RSS público y exploración regional."""

    def __init__(self, poll_interval_minutes: int = 15) -> None:
        super().__init__(
            name="ChileTrabajos",
            base_url="https://www.chiletrabajos.cl",
            source_type="rss",
            poll_interval_minutes=poll_interval_minutes,
            requires_auth=False,
            timeout_seconds=30,
            max_retries=3,
            rate_limit_delay=1.5,
        )
        # Feeds oficiales: General, Tecnología y Región de Ñuble (Región 16)
        self.feed_urls = [
            "https://www.chiletrabajos.cl/rss/",
            "https://www.chiletrabajos.cl/rss/categoria/informatica-telecomunicaciones",
            "https://www.chiletrabajos.cl/rss/region/nuble",
        ]

    async def fetch_jobs(
        self,
        session: aiohttp.ClientSession,
        criteria: Any | None = None,
    ) -> list[JobPayload]:
        """Consulta los feeds RSS de ChileTrabajos y extrae las ofertas normalizadas."""
        all_jobs: list[JobPayload] = []
        seen_urls: set[str] = set()

        for feed_url in self.feed_urls:
            try:
                xml_text = await self.request_get(session, feed_url)
                jobs = self._parse_rss_feed(xml_text)
                for j in jobs:
                    if j.url not in seen_urls:
                        seen_urls.add(j.url)
                        all_jobs.append(j)
            except Exception as e:
                logger.warning("[%s] Error consultando feed %s: %s", self.name, feed_url, e)

        if all_jobs:
            self.record_success(len(all_jobs))
        else:
            if self.last_error:
                self.record_error("No se pudieron extraer ofertas de los feeds RSS.")
            else:
                self.record_success(0)

        return all_jobs

    def _parse_rss_feed(self, xml_text: str) -> list[JobPayload]:
        """Parsea el XML de un feed RSS de ChileTrabajos."""
        try:
            soup = BeautifulSoup(xml_text, "xml")
        except Exception:
            soup = BeautifulSoup(xml_text, "html.parser")
        items = soup.find_all("item")
        if not items:
            soup = BeautifulSoup(xml_text, "html.parser")
            items = soup.find_all("item")

        parsed_jobs: list[JobPayload] = []
        for item in items:
            try:
                title_elem = item.find("title")
                link_elem = item.find("link")
                desc_elem = item.find("description")
                pub_elem = item.find("pubDate")
                guid_elem = item.find("guid")

                if not title_elem or not link_elem:
                    continue

                title = title_elem.get_text().strip()
                url = link_elem.get_text().strip()
                desc = desc_elem.get_text().strip() if desc_elem else ""
                guid = guid_elem.get_text().strip() if guid_elem else url

                published_at: datetime | None = None
                if pub_elem and pub_elem.get_text():
                    try:
                        published_at = parsedate_to_datetime(pub_elem.get_text().strip())
                        # Remover timezone para compatibilidad uniforme con naive datetime en UTC
                        if published_at.tzinfo is not None:
                            published_at = published_at.astimezone().replace(tzinfo=None)
                    except Exception:
                        published_at = None

                raw_data = {
                    "external_id": guid,
                    "title": title,
                    "url": url,
                    "description": desc,
                    "published_at": published_at,
                }

                # Normalizar oferta
                job_payload = normalize_job_payload(raw_data, source_name=self.name)
                # Asignar huella de deduplicación
                compute_job_fingerprint(job_payload)
                parsed_jobs.append(job_payload)
            except Exception as e:
                logger.debug("[%s] Error parseando item RSS: %s", self.name, e)
                continue

        return parsed_jobs
