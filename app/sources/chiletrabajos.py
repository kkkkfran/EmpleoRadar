"""Conector oficial para ChileTrabajos (https://www.chiletrabajos.cl/).

Consulta las páginas públicas de vacantes laborales enfocadas en Informática,
Región de Ñuble (Chillán) y Región del Biobío (Concepción y comunas aledañas).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

from app.jobs.deduplication import compute_job_fingerprint
from app.jobs.models import JobPayload
from app.jobs.normalizer import normalize_job_payload
from app.sources.base import BaseJobSource

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
    now = datetime.now()
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
        # Endpoints estratégicos: Informática en Concepción (1035), Chillán (1036), Nacional y Búsquedas por Cargo
        self.search_urls = [
            # 1. Informática en Concepción (Región del Biobío)
            "https://www.chiletrabajos.cl/encuentra-un-empleo?categoria=2007&13=1035",
            # 2. Informática en Chillán (Región de Ñuble)
            "https://www.chiletrabajos.cl/encuentra-un-empleo?categoria=2007&13=1036",
            # 3. Informática a nivel nacional (incluye vacantes remotas)
            "https://www.chiletrabajos.cl/encuentra-un-empleo?categoria=2007",
            # 4. Búsqueda específica por perfil Ingeniero en Informática
            "https://www.chiletrabajos.cl/encuentra-un-empleo?2=ingeniero+informatica",
            # 5. Búsqueda específica por perfil Desarrollador
            "https://www.chiletrabajos.cl/encuentra-un-empleo?2=desarrollador",
            # 6. Todas las ofertas generales en Chillán
            "https://www.chiletrabajos.cl/encuentra-un-empleo?13=1036",
            # 7. Ventas y Comercial en Chillán (tiendas, retail, asistentes)
            "https://www.chiletrabajos.cl/encuentra-un-empleo?categoria=2027&13=1036",
            # 8. Operarios y Bodega en Chillán (reponedores, empaque, bodega)
            "https://www.chiletrabajos.cl/encuentra-un-empleo?categoria=2025&13=1036",
            # 9. Logística y Distribución en Chillán
            "https://www.chiletrabajos.cl/encuentra-un-empleo?categoria=2021&13=1036",
            # 10. Búsqueda de reponedores y retail en Chillán
            "https://www.chiletrabajos.cl/encuentra-un-empleo?2=reponedor&13=1036",
            # 11. Todas las ofertas en Concepción
            "https://www.chiletrabajos.cl/encuentra-un-empleo?13=1035",
        ]

    async def fetch_jobs(
        self,
        session: aiohttp.ClientSession,
        criteria: Any | None = None,
    ) -> list[JobPayload]:
        """Consulta los listados de empleo de ChileTrabajos y extrae las ofertas normalizadas."""
        all_jobs: list[JobPayload] = []
        seen_urls: set[str] = set()

        for url in self.search_urls:
            try:
                response_text = await self.request_get(session, url)
                # Intentar parsear como página web con tarjetas job-item
                jobs = self._parse_html_job_items(response_text)
                if not jobs:
                    # Si fuera un feed XML/RSS
                    jobs = self._parse_rss_feed(response_text)

                for j in jobs:
                    if j.url not in seen_urls:
                        seen_urls.add(j.url)
                        all_jobs.append(j)
            except Exception as e:
                logger.warning("[%s] Error consultando %s: %s", self.name, url, e)

        if all_jobs:
            self.record_success(len(all_jobs))
        else:
            if self.last_error:
                self.record_error("No se pudieron extraer ofertas de ChileTrabajos.")
            else:
                self.record_success(0)

        return all_jobs

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

