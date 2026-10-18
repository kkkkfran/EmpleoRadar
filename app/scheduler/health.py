"""Monitoreo de salud del sistema, métricas y diagnóstico."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.database.repository import Repository
from app.sources.registry import SourceRegistry

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Proporciona información consolidada sobre el estado del bot, base de datos y fuentes."""

    def __init__(self, repository: Repository, source_registry: SourceRegistry) -> None:
        self.repo = repository
        self.source_registry = source_registry
        self.started_at = datetime.utcnow()

    async def get_system_health(self, discord_connected: bool = True) -> dict[str, Any]:
        """Recopila el estado completo de salud del sistema."""
        # 1. Base de datos
        db_healthy = True
        try:
            job_stats = await self.repo.get_job_stats()
        except Exception as e:
            logger.error("Error al consultar estado de la base de datos: %s", e)
            db_healthy = False
            job_stats = {"total": 0, "active": 0, "notified": 0}

        # 2. Fuentes
        sources_status: list[dict[str, Any]] = []
        all_sources = self.source_registry.list_sources()
        for src in all_sources:
            sources_status.append(
                {
                    "name": src.name,
                    "status": src.status.value,
                    "poll_interval": src.poll_interval_minutes,
                    "last_checked": src.last_checked_at.isoformat()
                    if src.last_checked_at
                    else None,
                    "consecutive_errors": src.consecutive_errors,
                    "last_error": src.last_error,
                }
            )

        uptime_seconds = int((datetime.utcnow() - self.started_at).total_seconds())

        return {
            "status": "operativo" if (db_healthy and discord_connected) else "degradado",
            "uptime_seconds": uptime_seconds,
            "discord_connected": discord_connected,
            "database_healthy": db_healthy,
            "job_stats": job_stats,
            "sources": sources_status,
        }
