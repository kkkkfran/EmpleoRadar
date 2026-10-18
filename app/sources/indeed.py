"""Conector para Indeed Chile (https://cl.indeed.com/).

Indeed prohíbe el scraping automatizado en sus Términos de Servicio y utiliza
controles Cloudflare/antibot. Este conector documenta la integración oficial
disponible exclusivamente vía Indeed Publisher/Partner API y soporta importación
manual legítima de enlaces compartidos en Discord.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from app.database.models import SourceStatus
from app.jobs.models import JobPayload
from app.sources.base import BaseJobSource

logger = logging.getLogger(__name__)


class IndeedSource(BaseJobSource):
    """Conector para Indeed Chile respetando condiciones legales y de servicio."""

    def __init__(self) -> None:
        super().__init__(
            name="Indeed Chile",
            base_url="https://cl.indeed.com",
            source_type="partner_api",
            poll_interval_minutes=60,
            requires_auth=True,
            timeout_seconds=30,
        )
        self.status = SourceStatus.LIMITADA
        self.access_notes = (
            "Indeed prohíbe explícitamente el scraping automatizado en sus ToS. "
            "El acceso por API requiere aprobación en el programa Indeed Partner. "
            "Soporta importación de vacantes compartidas directamente por el usuario."
        )

    async def fetch_jobs(
        self,
        session: aiohttp.ClientSession,
        criteria: Any | None = None,
    ) -> list[JobPayload]:
        """No realiza scraping no autorizado. Espera credencial oficial de partner o importación manual."""
        return []
