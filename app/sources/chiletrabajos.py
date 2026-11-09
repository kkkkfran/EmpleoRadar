"""Conector oficial para ChileTrabajos (https://www.chiletrabajos.cl/).

Consulta las páginas públicas de vacantes laborales enfocadas en Informática,
Región de Ñuble (Chillán) y Región del Biobío (Concepción y comunas aledañas).
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

import aiohttp
from bs4 import BeautifulSoup

from app.jobs.deduplication import compute_job_fingerprint
from app.jobs.models import JobPayload
from app.jobs.normalizer import normalize_job_payload
from app.sources.base import BaseJobSource, SourceError

logger = logging.getLogger(__name__)

MESES_ES: dict[str, int] = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


def parse_chiletrabajos_date(txt: str) -> datetime | None:
    """Parsea fechas en español tipo '15 de Octubre de 2026', 'Hoy', 'Ayer'."""
    if not txt:
        return None
    clean = txt.lower().strip()
    now = datetime.now(ZoneInfo("America/Santiago")).replace(tzinfo=None)
    if "hoy" in clean:
        return now.replace(hour=12, minute=0, second=0, microsecond=0)
    if "ayer" in clean:
        return (now - timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)

    m = re.search(r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4})", clean)
    if m:
        dia = int(m.group(1))
        mes_nombre = m.group(2)
        ano = int(m.group(3))
        mes_num = MESES_ES.get(mes_nombre)
        if mes_num:
            return datetime(ano, mes_num, dia, 12, 0, 0)
    return None


class ChileTrabajosSource(BaseJobSource):
    """Conector para ChileTrabajos mediante consulta de ofertas públicas."""

    def __init__(self, poll_interval_minutes: int = 15) -> None:
        super().__init__(
            name="ChileTrabajos",
            base_url="https://www.chiletrabajos.cl",
            source_type="public_web",
            poll_interval_minutes=poll_interval_minutes,
            requires_auth=False,
            timeout_seconds=30,
            max_retries=3,
            rate_limit_delay=1.0,
        )
        self.search_urls = [
            "https://www.chiletrabajos.cl/encuentra-un-empleo?13=1036&fecha=4",
            "https://www.chiletrabajos.cl/encuentra-un-empleo?2=remoto&fecha=4",
        ]
        self.recovery_days = 4
        self.max_pages = 3
        self._detail_cache: dict[str, JobPayload] = {}

    async def fetch_jobs(
        self,
        session: aiohttp.ClientSession,
        criteria: Any | None = None,
    ) -> list[JobPayload]:
        """Consulta los listados de empleo de ChileTrabajos y extrae las ofertas normalizadas."""
        all_jobs: list[JobPayload] = []
        seen_urls: set[str] = set()

        errors: list[str] = []
        successful = 0
        cutoff = (datetime.now(ZoneInfo("America/Santiago")) - timedelta(days=self.recovery_days)).date()
        for initial_url in self.search_urls:
            url = initial_url
            try:
                for page in range(self.max_pages):
                    response_text = await self.request_get(session, url)
                    jobs = self._parse_html_job_items(response_text)
                    successful += 1
                    for job in jobs:
                        if job.url in seen_urls or not job.published_at or job.published_at.date() < cutoff:
                            continue
                        seen_urls.add(job.url)
                        if job.url in self._detail_cache:
                            all_jobs.append(self._detail_cache[job.url])
                            continue
                        try:
                            detail = await self.request_get(session, job.url)
                            enriched = self._parse_detail(detail, job)
                            if len(self._detail_cache) >= 1000:
                                self._detail_cache.pop(next(iter(self._detail_cache)))
                            self._detail_cache[job.url] = enriched
                            all_jobs.append(enriched)
                        except Exception as exc:
                            errors.append(str(exc))
                    soup = BeautifulSoup(response_text, "html.parser")
                    next_link = next((a for a in soup.select(".pagination a") if a.get_text(strip=True) in {">", "»", "Siguiente"}), None)
                    if not next_link:
                        break
                    url = urljoin(url, str(next_link.get("href", "")))
                    if urlsplit(url).hostname != "www.chiletrabajos.cl":
                        break
                    if page + 1 == self.max_pages:
                        logger.warning("ChileTrabajos: limite de paginas alcanzado; consulta parcial")
            except Exception as exc:
                errors.append(str(exc))
                logger.warning("[%s] Error consultando %s: %s", self.name, url, exc)
        if not successful:
            error = errors[0] if errors else "No se pudo consultar ChileTrabajos"
            self.record_error(error)
            raise SourceError(error)
        if errors:
            self.record_error("Consulta parcial: " + errors[0])
        else:
            self.record_success(len(all_jobs))
        return all_jobs

    def _parse_detail(self, html_text: str, listing: JobPayload) -> JobPayload:
        soup = BeautifulSoup(html_text, "html.parser")
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                item = json.loads(script.get_text())
            except (ValueError, TypeError):
                continue
            if not isinstance(item, dict) or item.get("@type") != "JobPosting":
                continue
            published = listing.published_at
            if item.get("datePosted"):
                with contextlib.suppress(ValueError, TypeError):
                    published = datetime.fromisoformat(item["datePosted"])
            raw = {
                "external_id": listing.external_id, "url": listing.url,
                "title": item.get("title") or listing.title,
                "company": (item.get("hiringOrganization") or {}).get("name") or listing.company,
                "description": item.get("description") or listing.description,
                "location": listing.location_raw, "published_at": published,
                "requirements": item.get("qualifications"),
                "education_required": item.get("educationRequirements"),
            }
            result = normalize_job_payload(raw, self.name)
            compute_job_fingerprint(result)
            return result
        raise SourceError("Ficha ChileTrabajos sin JobPosting; no se pueden verificar requisitos")

    def _parse_html_job_items(self, html_text: str) -> list[JobPayload]:
        """Parsea las tarjetas HTML de ofertas laborales (.job-item) de ChileTrabajos."""
        soup = BeautifulSoup(html_text, "html.parser")
        items = soup.find_all("div", class_=lambda c: c and "job-item" in c)
        if not items:
            return []

        parsed_jobs: list[JobPayload] = []
        for it in items:
            try:
                title_elem = it.find("h2") or it.find("a")
                link_elem = it.find("a")
                if not title_elem or not link_elem:
                    continue

                title = title_elem.get_text(strip=True)
                url = link_elem.get("href", "").strip()
                if not url:
                    continue
                if not url.startswith("http"):
                    url = f"https://www.chiletrabajos.cl{url}"

                # ID externo (del botón guardar o de los dígitos al final de la URL)
                btn_save = it.find("a", class_="guardar")
                external_id = btn_save.get("data-id") if btn_save else None
                if not external_id:
                    m = re.search(r"-(\d+)$", url)
                    external_id = m.group(1) if m else url

                # Metadatos: Empresa, Ubicación y Fecha
                meta_elements = it.find_all("h3")
                company = None
                location = None
                published_at = None

                if len(meta_elements) >= 1:
                    empresa_loc = meta_elements[0].get_text(strip=True)
                    if "," in empresa_loc:
                        parts = empresa_loc.split(",", 1)
                        company = parts[0].strip() or None
                        location = parts[1].strip() or None
                    else:
                        company = empresa_loc or None

                if len(meta_elements) >= 2:
                    fecha_txt = meta_elements[1].get_text(strip=True)
                    published_at = parse_chiletrabajos_date(fecha_txt)

                # Descripción
                desc_elem = it.find("p", class_="description") or it.find("p")
                desc = desc_elem.get_text(separator=" ", strip=True) if desc_elem else ""

                raw_data = {
                    "external_id": str(external_id),
                    "title": title,
                    "url": url,
                    "company": company,
                    "location": location,
                    "description": desc,
                    "published_at": published_at,
                }

                payload = normalize_job_payload(raw_data, source_name=self.name)
                compute_job_fingerprint(payload)
                parsed_jobs.append(payload)
            except Exception as e:
                logger.debug("[%s] Error parseando job-item: %s", self.name, e)
                continue

        return parsed_jobs

    def _parse_rss_feed(self, xml_text: str) -> list[JobPayload]:
        """Parsea el XML si la respuesta corresponde a un feed RSS."""
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

                job_payload = normalize_job_payload(raw_data, source_name=self.name)
                compute_job_fingerprint(job_payload)
                parsed_jobs.append(job_payload)
            except Exception as e:
                logger.debug("[%s] Error parseando item RSS: %s", self.name, e)
                continue

        return parsed_jobs

