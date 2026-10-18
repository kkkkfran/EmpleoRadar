"""Conector genérico para cualquier fuente RSS o Atom de ofertas de trabajo."""

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


class GenericRSSSource(BaseJobSource):
    """Conector genérico para feeds RSS o Atom."""

    def __init__(
        self,
        name: str,
        feed_url: str,
        poll_interval_minutes: int = 15,
    ) -> None:
        super().__init__(
            name=name,
            base_url=feed_url,
            source_type="rss",
            poll_interval_minutes=poll_interval_minutes,
            requires_auth=False,
            timeout_seconds=30,
            max_retries=3,
        )
        self.feed_url = feed_url

    async def fetch_jobs(
        self,
        session: aiohttp.ClientSession,
        criteria: Any | None = None,
    ) -> list[JobPayload]:
        """Consulta el feed RSS configurado."""
        try:
            xml_text = await self.request_get(session, self.feed_url)
            jobs = self._parse_feed(xml_text)
            self.record_success(len(jobs))
            return jobs
        except Exception as e:
            self.record_error(str(e))
            return []

    def _parse_feed(self, content: str) -> list[JobPayload]:
        try:
            soup = BeautifulSoup(content, "xml")
        except Exception:
            soup = BeautifulSoup(content, "html.parser")
        items = soup.find_all("item")
        if not items:
            # Intentar formato Atom (<entry>)
            items = soup.find_all("entry")

        results: list[JobPayload] = []
        for item in items:
            try:
                title_elem = item.find("title")
                link_elem = item.find("link")
                desc_elem = item.find(["description", "summary", "content"])
                pub_elem = item.find(["pubDate", "published", "updated"])
                guid_elem = item.find(["guid", "id"])

                if not title_elem:
                    continue

                title = title_elem.get_text().strip()
                url = ""
                if link_elem:
                    url = link_elem.get("href") or link_elem.get_text().strip()

                if not url:
                    continue

                desc = desc_elem.get_text().strip() if desc_elem else ""
                guid = guid_elem.get_text().strip() if guid_elem else url

                published_at: datetime | None = None
                if pub_elem and pub_elem.get_text():
                    try:
                        published_at = parsedate_to_datetime(pub_elem.get_text().strip())
                        if published_at.tzinfo is not None:
                            published_at = published_at.astimezone().replace(tzinfo=None)
                    except Exception:
                        pass

                raw = {
                    "external_id": guid,
                    "title": title,
                    "url": url,
                    "description": desc,
                    "published_at": published_at,
                }

                payload = normalize_job_payload(raw, source_name=self.name)
                compute_job_fingerprint(payload)
                results.append(payload)
            except Exception as e:
                logger.debug("[%s] Error parseando item genérico: %s", self.name, e)
                continue

        return results
