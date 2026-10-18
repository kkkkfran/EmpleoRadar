"""Conector para Trabajando.com (https://www.trabajando.cl/).

Trabajando.com requiere autenticación institucional o API de partners para consultas
automatizadas masivas. Este conector documenta sus restricciones, opera en modo asistido
y permite procesar enlaces de vacantes compartidos por el usuario.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from app.database.models import SourceStatus
from app.jobs.models import JobPayload
from app.sources.base import BaseJobSource

logger = logging.getLogger(__name__)


class TrabajandoSource(BaseJobSource):
    """Conector para Trabajando.com en modo institucional/asistido."""

    def __init__(self) -> None:
        super().__init__(
            name="Trabajando.com",
            base_url="https://www.trabajando.cl",
            source_type="api_asistida",
            poll_interval_minutes=60,
            requires_auth=True,
            timeout_seconds=30,
        )
        self.status = SourceStatus.LIMITADA
        self.access_notes = (
            "Acceso automatizado masivo restringido por términos de servicio. "
            "Se requiere credencial API institucional para sondeo continuo. "
            "Soporta importación directa mediante enlace oficial proporcionado por el usuario."
        )

    async def fetch_jobs(
        self,
        session: aiohttp.ClientSession,
        criteria: Any | None = None,
    ) -> list[JobPayload]:
        """El sondeo automático directo no está habilitado sin credenciales API autorizadas."""
        logger.info(
            "[%s] Sondeo automático en pausa (requiere credencial API autorizada).", self.name
        )
        return []
