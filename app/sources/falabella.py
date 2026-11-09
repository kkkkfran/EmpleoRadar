"""Estado de la integración oficial Falabella/Aira, sin eludir sus controles."""

from typing import Any

import aiohttp

from app.database.models import SourceStatus
from app.jobs.models import JobPayload
from app.sources.base import BaseJobSource


class FalabellaSource(BaseJobSource):
    """Portal real registrado como limitado hasta disponer de acceso automatizado."""

    def __init__(self) -> None:
        super().__init__(
            name="Grupo Falabella / Aira",
            base_url="https://falabella.airavirtual.com/",
            source_type="manual",
            poll_interval_minutes=60,
        )
        self.status = SourceStatus.LIMITADA
        self.access_notes = (
            "Portal oficial de empleos del Grupo Falabella. La consulta automatizada "
            "devolvió HTTP 403 el 2026-11-09; no hay API pública verificada. "
            "Sin sondeo automático. Aira ofrece 'Seguir empresa' con inicio de sesión: "
            "https://jobs.airavirtual.com/falabella_corporativo . "
            "Las ofertas publicadas en otras fuentes activas sí se pueden detectar."
        )

    async def fetch_jobs(
        self, session: aiohttp.ClientSession, criteria: Any | None = None
    ) -> list[JobPayload]:
        return []
