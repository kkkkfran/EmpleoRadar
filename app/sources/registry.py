"""Registro central y ciclo de vida de fuentes de empleo."""

from __future__ import annotations

import logging

from app.database.repository import Repository
from app.sources.base import BaseJobSource
from app.sources.bne import BNESource
from app.sources.chiletrabajos import ChileTrabajosSource
from app.sources.company_sites import CompanySitesSource
from app.sources.indeed import IndeedSource
from app.sources.rss import GenericRSSSource
from app.sources.trabajando import TrabajandoSource

logger = logging.getLogger(__name__)


class SourceRegistry:
    """Administra las fuentes de empleo registradas en el sistema."""

    def __init__(self, repository: Repository) -> None:
        self.repo = repository
        self._sources: dict[str, BaseJobSource] = {}
        self._register_default_sources()

    def _register_default_sources(self) -> None:
        """Registra los conectores predeterminados."""
        sources = [
            ChileTrabajosSource(),
            BNESource(),
            TrabajandoSource(),
            IndeedSource(),
            CompanySitesSource(),
        ]
        for src in sources:
            self._sources[src.name] = src

    def register_custom_rss(self, name: str, feed_url: str, interval: int = 15) -> GenericRSSSource:
        """Registra un nuevo feed RSS personalizado."""
        src = GenericRSSSource(name=name, feed_url=feed_url, poll_interval_minutes=interval)
        self._sources[name] = src
        return src

    def get_source(self, name: str) -> BaseJobSource | None:
        """Obtiene una fuente por su nombre."""
        return self._sources.get(name)

    def list_sources(self) -> list[BaseJobSource]:
        """Lista todas las fuentes registradas en memoria."""
        return list(self._sources.values())

    async def sync_with_database(self) -> None:
        """Sincroniza el registro de fuentes con la base de datos."""
        for src in self._sources.values():
            db_source = await self.repo.get_or_create_source(
                name=src.name,
                url=src.base_url,
                source_type=src.source_type,
                poll_interval_minutes=src.poll_interval_minutes,
                requires_auth=src.requires_auth,
                access_notes=getattr(src, "access_notes", None),
                status=src.status.value,
            )
            # Si en BD fue deshabilitada, reflejar en memoria
            if not db_source.is_enabled:
                logger.info("Fuente %s deshabilitada por configuración en base de datos.", src.name)

    def get_active_sources(self) -> list[BaseJobSource]:
        """Retorna las fuentes operativas listas para sondeo."""
        return [
            s
            for s in self._sources.values()
            if not s.requires_auth and s.source_type in ("rss", "public_web")
        ]
