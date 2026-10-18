"""Punto de entrada principal para ejecutar el bot EmpleoRadar."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import sys

from app.applications.service import ApplicationService
from app.bot.client import EmpleoRadarBot
from app.config import get_settings
from app.database.migrations.runner import run_migrations
from app.database.repository import Database, Repository
from app.logging_config import setup_logging
from app.profile.cv_storage import CVStorage
from app.profile.service import ProfileService
from app.scheduler.health import HealthMonitor
from app.scheduler.runner import JobSchedulerRunner
from app.sources.registry import SourceRegistry

logger = logging.getLogger("empleoradar.main")


async def main() -> None:
    """Función de arranque asíncrona de EmpleoRadar."""
    # 1. Cargar y validar configuración
    try:
        settings = get_settings()
    except SystemExit as se:
        print(f"\n❌ ERROR DE CONFIGURACIÓN:\n{se}\n", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error fatal al inicializar configuración:\n{e}\n", file=sys.stderr)
        sys.exit(1)

    # 2. Inicializar sistema de logs estructurado y redacción
    setup_logging(level=settings.log_level, log_dir=settings.base_dir / "logs")
    logger.info("Iniciando EmpleoRadar v0.1.0 (Zona horaria: %s)", settings.timezone)

    # 3. Crear directorios necesarios
    settings.ensure_directories()

    # 4. Conexión a Base de Datos y Migraciones
    db = Database(settings.database_url)
    await db.create_tables()
    applied = await run_migrations(db)
    logger.info("Migraciones verificadas. Nuevas aplicadas: %d", applied)

    repo = Repository(db)

    # 5. Servicios de Dominio
    cv_storage = CVStorage(settings.cv_storage_path)
    profile_service = ProfileService(repo, cv_storage)
    app_service = ApplicationService(
        repo,
        profile_service,
        require_confirmation=settings.application_require_confirmation,
    )
    source_registry = SourceRegistry(repo)
    health_monitor = HealthMonitor(repo, source_registry)

    # Asegurar registro inicial del propietario
    await repo.get_or_create_owner(settings.discord_owner_id)

    # 6. Cliente del Bot de Discord
    bot = EmpleoRadarBot(
        settings=settings,
        repository=repo,
        profile_service=profile_service,
        app_service=app_service,
        source_registry=source_registry,
        health_monitor=health_monitor,
    )

    # 7. Planificador de Sondeo de Ofertas
    scheduler_runner = JobSchedulerRunner(
        repository=repo,
        source_registry=source_registry,
        owner_id=settings.discord_owner_id,
        notification_callback=bot.notify_new_job,
        poll_interval_minutes=settings.poll_interval_minutes,
        max_concurrent_requests=settings.max_concurrent_requests,
    )
    bot.scheduler_runner = scheduler_runner

    # 8. Manejo de señales de apagado controlado (Graceful Shutdown)
    stop_event = asyncio.Event()

    def signal_handler() -> None:
        logger.info("Señal de apagado recibida. Deteniendo servicios...")
        stop_event.set()

    # Registrar señales en sistemas POSIX y Windows
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, signal_handler)

    try:
        # Iniciar planificador
        await scheduler_runner.start()

        # Iniciar bot de Discord
        async with bot:
            logger.info("Conectando bot a Discord...")
            bot_task = asyncio.create_task(bot.start(settings.discord_bot_token))

            # Esperar a que el bot termine o se solicite apagado
            done, pending = await asyncio.wait(
                [bot_task, asyncio.create_task(stop_event.wait())],
                return_when=asyncio.FIRST_COMPLETED,
            )

            if bot_task in done and bot_task.exception():
                logger.error("Error en bot de Discord: %s", bot_task.exception())

    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Interrupción detectada. Cerrando EmpleoRadar...")
    finally:
        logger.info("Apagando planificador y cerrando base de datos...")
        await scheduler_runner.stop()
        await db.close()
        logger.info("✅ EmpleoRadar detenido de manera segura.")


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
