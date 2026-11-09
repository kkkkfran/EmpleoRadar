"""Arranque, apagado y disponibilidad sin conectar a Discord real."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from app.main import run_bot_services
from app.scheduler.http_health import HealthServer, validate_persistent_storage


class FakeBot:
    def __init__(self, failure=None):
        self.settings = SimpleNamespace(discord_bot_token="test-token")
        self.ready = asyncio.Event()
        self.connecting = asyncio.Event()
        self.closed = asyncio.Event()
        self.failure = failure

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def start(self, token):
        self.connecting.set()
        if self.failure:
            raise self.failure
        await self.closed.wait()

    async def close(self):
        self.closed.set()

    async def wait_until_ready(self):
        await self.ready.wait()


def scheduler_mock():
    return SimpleNamespace(start=AsyncMock(), stop=AsyncMock(), initialize_baseline=AsyncMock())


async def test_scanning_waits_for_discord_and_shutdown_cleans_tasks():
    bot = FakeBot()
    scheduler = scheduler_mock()
    recovered = asyncio.Event()
    scheduler.initialize_baseline.side_effect = recovered.set
    stop = asyncio.Event()
    task = asyncio.create_task(run_bot_services(bot, scheduler, stop))
    await asyncio.wait_for(bot.connecting.wait(), 1)
    scheduler.start.assert_not_awaited()
    bot.ready.set()
    await asyncio.wait_for(recovered.wait(), 1)
    stop.set()
    await asyncio.wait_for(task, 1)
    scheduler.start.assert_awaited_once()
    scheduler.initialize_baseline.assert_awaited_once()
    scheduler.stop.assert_awaited_once()
    assert bot.closed.is_set()


async def test_invalid_token_fails_process_instead_of_clean_exit():
    bot = FakeBot(ValueError("Invalid credential"))
    scheduler = scheduler_mock()
    with pytest.raises(ValueError, match="Invalid credential"):
        await run_bot_services(bot, scheduler, asyncio.Event())
    scheduler.start.assert_not_awaited()
    scheduler.stop.assert_awaited_once()
    assert bot.closed.is_set()


async def test_recovery_failure_is_supervised():
    bot = FakeBot()
    bot.ready.set()
    scheduler = scheduler_mock()
    scheduler.initialize_baseline.side_effect = RuntimeError("Database unavailable")
    with pytest.raises(RuntimeError, match="Database unavailable"):
        await run_bot_services(bot, scheduler, asyncio.Event())
    assert bot.closed.is_set()


@pytest.mark.parametrize("broken", [None, "discord", "database", "scheduler", "stale"])
async def test_health_endpoint_detects_actual_runtime_failures(broken):
    bot = SimpleNamespace(is_ready=Mock(return_value=broken != "discord"))
    now = datetime.now(UTC)
    scheduler = SimpleNamespace(
        _is_running=broken != "scheduler", poll_interval_minutes=2,
        last_cycle_completed_at=now - timedelta(hours=1) if broken == "stale" else now,
        last_cycle_started_at=now,
    )
    repo = SimpleNamespace(get_job_stats=AsyncMock(return_value={}))
    if broken == "database":
        repo.get_job_stats.side_effect = RuntimeError("private connection details")
    server = HealthServer(bot, scheduler, repo)
    app = web.Application()
    app.router.add_get("/health", server.check)
    async with TestClient(TestServer(app)) as client:
        response = await client.get("/health")
        assert response.status == (200 if broken is None else 503)
        assert "private" not in await response.text()


def test_railway_requires_database_inside_volume(monkeypatch, tmp_path):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "test")
    monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH", raising=False)
    settings = SimpleNamespace(database_url=f"sqlite+aiosqlite:///{tmp_path}/db.sqlite")
    with pytest.raises(RuntimeError, match="volumen"):
        validate_persistent_storage(settings)
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(tmp_path / "other"))
    with pytest.raises(RuntimeError, match="dentro"):
        validate_persistent_storage(settings)
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(tmp_path))
    validate_persistent_storage(settings)
