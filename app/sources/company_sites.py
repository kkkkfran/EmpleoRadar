"""Conector para páginas públicas de empleo de empresas tecnológicas en Chile."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from app.database.models import SourceStatus
from app.jobs.models import JobPayload
from app.sources.base import BaseJobSource

logger = logging.getLogger(__name__)


class CompanySitesSource(BaseJobSource):
    """Conector para consultar páginas de empleo de empresas o portales de reclutamiento abiertos."""

    def __init__(self) -> None:
        super().__init__(
            name="Empresas TI Chile",
            base_url="https://chile.direct-jobs.local",
            source_type="custom_api",
            poll_interval_minutes=60,
            requires_auth=False,
        )
        self.status = SourceStatus.OPERATIVA
        self.access_notes = (
            "Permite registrar feeds y APIs de carreras de empresas locales en Ñuble y Chile."
        )

    async def fetch_jobs(
        self,
        session: aiohttp.ClientSession,
        criteria: Any | None = None,
    ) -> list[JobPayload]:
        """Extrae ofertas de sitios de empresas directamente configurados."""
        return []
