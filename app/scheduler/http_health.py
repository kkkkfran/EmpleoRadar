"""Endpoint de disponibilidad para Docker y Railway, sin datos personales."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from aiohttp import web


class HealthServer:
    def __init__(self, bot, scheduler, repository, port: int = 8080) -> None:
        self.bot = bot
        self.scheduler = scheduler
        self.repository = repository
        self.port = port
        self._runner: web.AppRunner | None = None

    async def check(self, request: web.Request) -> web.Response:
        database_ready = False
        try:
            async with asyncio.timeout(3):
                await self.repository.get_job_stats()
                database_ready = True
        except Exception:
            pass
        connected = self.bot.is_ready()
        running = self.scheduler._is_running
        last_cycle = self.scheduler.last_cycle_completed_at
        last_activity = last_cycle or self.scheduler.last_cycle_started_at
        fresh = True
        if last_activity:
            # Las fechas del scheduler se almacenan en UTC sin zona, como SQLite.
            if last_activity.tzinfo is None:
                last_activity = last_activity.replace(tzinfo=UTC)
            max_age = max(900, self.scheduler.poll_interval_minutes * 180)
            fresh = (datetime.now(UTC) - last_activity).total_seconds() < max_age
        healthy = database_ready and connected and running and fresh
        return web.json_response(
            {
                "status": "ok" if healthy else "unavailable",
                "discord_connected": connected,
                "database_ready": database_ready,
                "scheduler_running": running,
                "scanner_fresh": fresh,
                "last_cycle_completed_at": last_cycle.isoformat() if last_cycle else None,
            },
            status=200 if healthy else 503,
        )

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/health", self.check)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        await web.TCPSite(self._runner, host="0.0.0.0", port=self.port).start()

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()


def validate_persistent_storage(settings) -> None:
    """Evita arrancar en Railway con SQLite fuera de su volumen persistente."""
    import os
    from pathlib import Path

    from sqlalchemy.engine import make_url

    if not os.environ.get("RAILWAY_ENVIRONMENT_ID"):
        return
    db_url = make_url(settings.database_url)
    if db_url.get_backend_name() != "sqlite":
        return
    mount = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    if not mount:
        raise RuntimeError("Conecta un volumen Railway en /app/data antes de iniciar el bot.")
    database_path = Path(db_url.database or "").resolve()
    if not database_path.is_relative_to(Path(mount).resolve()):
        raise RuntimeError("DATABASE_URL debe apuntar dentro del volumen persistente de Railway.")
