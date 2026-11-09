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


# --- Migraciones Registradas ---


@register_migration("001", "Esquema inicial de base de datos")
async def migrate_001(session: AsyncSession) -> None:
    """Marcador del esquema inicial (tablas creadas por create_all)."""
    pass


@register_migration("002", "Agregar columna notification_channel_id a candidate_preferences")
async def migrate_002(session: AsyncSession) -> None:
    """Agrega notification_channel_id a candidate_preferences si la tabla ya existía."""
    import contextlib

    from sqlalchemy import text

    with contextlib.suppress(Exception):
        await session.execute(
            text("ALTER TABLE candidate_preferences ADD COLUMN notification_channel_id INTEGER")
        )


@register_migration("003", "Agregar canales separados para informatica y chillan")
async def migrate_003(session: AsyncSession) -> None:
    """Agrega channel_informatica_id y channel_chillan_id a candidate_preferences."""
    import contextlib

    from sqlalchemy import text

    with contextlib.suppress(Exception):
        await session.execute(
            text("ALTER TABLE candidate_preferences ADD COLUMN channel_informatica_id INTEGER")
        )
    with contextlib.suppress(Exception):
        await session.execute(
            text("ALTER TABLE candidate_preferences ADD COLUMN channel_chillan_id INTEGER")
        )


@register_migration("004", "Agregar decisión personal a las ofertas")
async def migrate_004(session: AsyncSession) -> None:
    """Persiste pendiente, postulado o descartado para cada oferta."""
    import contextlib

    from sqlalchemy import text

    with contextlib.suppress(Exception):
        await session.execute(
            text("ALTER TABLE jobs ADD COLUMN user_decision VARCHAR(20) DEFAULT 'pending' NOT NULL")
        )


@register_migration("005", "Separar inventario inicial de notificaciones pendientes")
async def migrate_005(session: AsyncSession) -> None:
    """Conserva el inventario sin inventar entregas ni fechas de publicación."""
    from sqlalchemy import inspect, text

    connection = await session.connection()
    columns = await connection.run_sync(
        lambda sync_connection: {c["name"] for c in inspect(sync_connection).get_columns("jobs")}
    )
    if "notification_eligible" not in columns:
        await session.execute(
            text("ALTER TABLE jobs ADD COLUMN notification_eligible BOOLEAN DEFAULT 1 NOT NULL")
        )
        # Las versiones anteriores no distinguían inventario sin fecha de una
        # notificación que realmente se intentó enviar. No prometer antigüedad.
        await session.execute(
            text(
                "UPDATE jobs SET notification_eligible = 0 "
                "WHERE published_at IS NULL AND notified = 0 "
                "AND notification_message_id IS NULL"
            )
        )


