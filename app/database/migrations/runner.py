"""Sistema de migraciones para EmpleoRadar."""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import SchemaMigration
from app.database.repository import Database

logger = logging.getLogger(__name__)

# Registry of migrations: (version, description, migration_func)
_MIGRATIONS: list[tuple[str, str, Callable[[AsyncSession], Coroutine[Any, Any, None]]]] = []


def register_migration(version: str, description: str) -> Callable:
    """Decorador para registrar una migración."""

    def decorator(func: Callable[[AsyncSession], Coroutine[Any, Any, None]]) -> Callable:
        _MIGRATIONS.append((version, description, func))
        return func

    return decorator


async def run_migrations(db: Database) -> int:
    """Ejecuta las migraciones pendientes.

    Returns:
        Number of migrations applied.
    """
    applied_count = 0

    async with db.session() as session:
        # Get already-applied versions
        try:
            result = await session.execute(select(SchemaMigration.version))
            applied_versions = {row[0] for row in result.all()}
        except Exception:
            # Table might not exist yet on first run
            applied_versions = set()

    # Sort migrations by version
    sorted_migrations = sorted(_MIGRATIONS, key=lambda m: m[0])

    for version, description, migrate_func in sorted_migrations:
        if version in applied_versions:
            logger.debug("Migración %s ya aplicada, saltando", version)
            continue

        logger.info("Aplicando migración %s: %s", version, description)
        async with db.session() as session:
            try:
                await migrate_func(session)

                # Record the migration
                migration = SchemaMigration(
                    version=version,
                    description=description,
                )
                session.add(migration)
                await session.commit()
                applied_count += 1
                logger.info("Migración %s aplicada exitosamente", version)
            except Exception as exc:
                await session.rollback()
                logger.error("Error aplicando migración %s: %s", version, exc, exc_info=True)
                raise RuntimeError(f"Migración {version} falló: {exc}") from exc

    if applied_count == 0:
        logger.info("No hay migraciones pendientes")
    else:
        logger.info("Se aplicaron %d migraciones", applied_count)

    return applied_count


async def get_migration_status(db: Database) -> list[dict[str, Any]]:
    """Obtiene el estado de todas las migraciones.

    Returns:
        List of dicts with version, description, applied status, and applied_at.
    """
    async with db.session() as session:
        try:
            result = await session.execute(
                select(SchemaMigration).order_by(SchemaMigration.version)
            )
            applied = {m.version: m for m in result.scalars().all()}
        except Exception:
            applied = {}

    sorted_migrations = sorted(_MIGRATIONS, key=lambda m: m[0])
    status_list: list[dict[str, Any]] = []

    for version, description, _ in sorted_migrations:
        migration = applied.get(version)
        status_list.append(
            {
                "version": version,
                "description": description,
                "applied": version in applied,
                "applied_at": migration.applied_at if migration else None,
            }
        )

    return status_list
