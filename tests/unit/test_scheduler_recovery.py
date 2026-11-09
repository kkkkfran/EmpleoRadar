"""Comportamiento observable de recuperación, reinicios y entregas fallidas."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from app.database.migrations.runner import run_migrations
from app.database.repository import Database, Repository
from app.jobs.models import JobPayload
from app.scheduler.runner import JobSchedulerRunner
from app.sources.base import BaseJobSource
from app.sources.registry import SourceRegistry

NOW = datetime.now(UTC).replace(tzinfo=None)


class ControlledSource(BaseJobSource):
    def __init__(self, jobs=(), name="Controlled", behavior=None):
        super().__init__(name=name, base_url="https://example.com", source_type="public_api")
        self.jobs = list(jobs)
        self.behavior = behavior
        self.calls = 0

    async def fetch_jobs(self, session, criteria=None):
        self.calls += 1
        if self.behavior:
            await self.behavior()
        self.record_success(len(self.jobs))
        return self.jobs


def job(identifier, published=NOW - timedelta(hours=1), source="Controlled"):
    return JobPayload(
        source_name=source, external_id=identifier, title=f"Vacante {identifier}",
        url=f"https://example.com/{identifier}", published_at=published,
        comuna="Chillán", region="Ñuble",
    )


@pytest.fixture
async def repo(tmp_path, monkeypatch):
    monkeypatch.setattr("app.scheduler.runner._now", lambda: NOW)
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'jobs.db'}")
    await db.create_tables()
    await run_migrations(db)
    yield Repository(db)
    await db.close()


@asynccontextmanager
async def running(repo, sources, callback, **options):
    registry = SourceRegistry(repo)
    registry._sources = {source.name: source for source in sources}
    runner = JobSchedulerRunner(
        repo, registry, 123, callback, notification_delay_seconds=0, **options
    )
    await runner.start()
    try:
        yield runner
    finally:
        await runner.stop()


async def test_recovery_only_recent_real_publication_and_no_unknown_flood(repo):
    source = ControlledSource([
        job("recent", NOW - timedelta(hours=1)),
        job("old", NOW - timedelta(days=4, seconds=1)),
        job("boundary", NOW - timedelta(days=4)),
        job("undated", None),
        job("future", NOW + timedelta(hours=1)),
    ])
    callback = AsyncMock(return_value=999)
    async with running(repo, [source], callback) as runner:
        assert await runner.initialize_baseline() == 2
        assert [call.args[0].external_id for call in callback.await_args_list] == ["boundary", "recent"]
        assert await runner.initialize_baseline() == 0
        await runner.scan_and_dispatch_cycle()
        assert callback.await_count == 2
        saved = await repo.search_jobs("undated")
        assert len(saved) == 1
        assert saved[0].notification_eligible is False
        assert saved[0].notified is False
        assert (await repo.get_job_stats())["total"] == 3
        assert runner.last_cycle_started_at == NOW
        assert runner.last_cycle_completed_at == NOW
    # Reiniciar tampoco convierte el inventario sin fecha en una novedad.
    async with running(repo, [source], callback) as runner:
        await runner.initialize_baseline()
        await runner.scan_and_dispatch_cycle()
    assert callback.await_count == 2


async def test_failed_notification_retried_after_listing_disappears_and_restart(repo):
    source = ControlledSource([job("retry")])
    callback = AsyncMock(side_effect=RuntimeError("Discord no disponible"))
    async with running(repo, [source], callback) as runner:
        assert await runner.initialize_baseline() == 0
    assert callback.await_count == 1
    assert (await repo.get_job_stats())["notified"] == 0
    source.jobs = []
    callback = AsyncMock(return_value=777)
    async with running(repo, [source], callback) as runner:
        assert await runner.initialize_baseline() == 1
        assert await runner.scan_and_dispatch_cycle() == 0
    assert callback.await_count == 1
    assert (await repo.get_job_stats())["total"] == 1
    stored = (await repo.search_jobs("retry"))[0]
    assert stored.notification_message_id == 777


async def test_new_undated_live_job_retries_after_restart(repo):
    source = ControlledSource()
    callback = AsyncMock(return_value=None)
    async with running(repo, [source], callback) as runner:
        await runner.initialize_baseline()
        source.jobs = [job("arrived", None)]
        await runner.scan_and_dispatch_cycle()
    assert callback.await_count == 1
    source.jobs = []
    callback = AsyncMock(return_value=888)
    async with running(repo, [source], callback) as runner:
        assert await runner.initialize_baseline() == 1
    assert callback.await_args.args[0].published_at is None


async def test_known_date_can_promote_unknown_baseline(repo):
    source = ControlledSource([job("dated-later", None)])
    callback = AsyncMock(return_value=1234)
    async with running(repo, [source], callback) as runner:
        await runner.initialize_baseline()
        assert callback.await_count == 0
        source.jobs = [job("dated-later")]
        assert await runner.scan_and_dispatch_cycle() == 1
    assert callback.await_count == 1


async def test_fast_source_delivers_before_slow_source_finishes(repo):
    delivered = asyncio.Event()
    slow_finished = False

    async def slow_fetch():
        nonlocal slow_finished
        await asyncio.wait_for(delivered.wait(), timeout=1)
        slow_finished = True
        raise RuntimeError("Portal temporalmente fuera de servicio")

    slow = ControlledSource(name="Slow", behavior=slow_fetch)
    fast = ControlledSource([job("fast", source="Fast")], name="Fast")

    async def notify(payload, match, job_id):
        assert not slow_finished
        delivered.set()
        return 123

    async with running(repo, [slow, fast], notify, max_concurrent_requests=2) as runner:
        assert await runner.initialize_baseline() == 1
        assert "Slow" not in runner._initialized_sources
        assert "Fast" in runner._initialized_sources
    sources = {source.name: source for source in await repo.get_all_sources()}
    assert sources["Slow"].consecutive_errors == 1
    assert sources["Fast"].consecutive_errors == 0


async def test_failed_initial_source_retries_recovery_without_unknown_flood(repo):
    async def failure():
        raise RuntimeError("HTTP 503")

    source = ControlledSource(behavior=failure)
    callback = AsyncMock(return_value=123)
    async with running(repo, [source], callback) as runner:
        assert await runner.initialize_baseline() == 0
        source.behavior = None
        source.jobs = [job("recovered"), job("unknown", None)]
        assert await runner.scan_and_dispatch_cycle() == 1
        await runner.scan_and_dispatch_cycle()
        assert callback.await_count == 1
        source.jobs.append(job("new-live", None))
        assert await runner.scan_and_dispatch_cycle() == 1


async def test_timed_out_source_does_not_prevent_other_deliveries(repo):
    async def hang():
        await asyncio.Event().wait()

    slow = ControlledSource(name="Slow", behavior=hang)
    fast = ControlledSource([job("fast", source="Fast")], name="Fast")
    callback = AsyncMock(return_value=1)
    async with running(repo, [slow, fast], callback, source_timeout_seconds=0.05) as runner:
        assert await runner.initialize_baseline() == 1
    sources = {source.name: source for source in await repo.get_all_sources()}
    assert "Tiempo máximo" in sources["Slow"].last_error
    assert callback.await_count == 1


async def test_aware_cutoff_is_utc_and_manual_date_cannot_widen_window(repo):
    chilean_boundary = (NOW - timedelta(days=4)).replace(tzinfo=UTC).astimezone(
        timezone(timedelta(hours=-3))
    )
    source = ControlledSource([job("boundary", chilean_boundary), job("older", NOW - timedelta(days=5))])
    callback = AsyncMock(return_value=1)
    async with running(repo, [source], callback) as runner:
        assert await runner.run_all_sources_now(NOW - timedelta(days=30)) == 1
    assert callback.await_args.args[0].external_id == "boundary"


async def test_paused_notifications_and_overlapping_cycles(repo):
    entered, release = asyncio.Event(), asyncio.Event()

    async def block():
        entered.set()
        await release.wait()

    source = ControlledSource([job("single")], behavior=block)
    callback = AsyncMock(return_value=1)
    async with running(repo, [source], callback) as runner:
        first = asyncio.create_task(runner.scan_and_dispatch_cycle())
        await entered.wait()
        assert await runner.scan_and_dispatch_cycle() == 0
        release.set()
        assert await first == 1
        owner = await repo.get_or_create_owner(123)
        await repo.update_preferences(owner.id, is_paused=True)
        assert await runner.scan_and_dispatch_cycle() == 0
    assert callback.await_count == 1
    assert source.calls == 1


async def test_filter_rejection_is_not_a_pending_notification(repo):
    source = ControlledSource([job("filtered")])
    callback = AsyncMock(return_value=1)
    async with running(repo, [source], callback, job_filter=lambda payload: False) as runner:
        await runner.initialize_baseline()
    assert callback.await_count == 0
    assert len(await repo.get_unnotified_jobs()) == 0
    saved = (await repo.search_jobs("filtered"))[0]
    assert saved.notified is False


async def test_legacy_recovery_preserves_any_evidence_of_delivery(repo):
    source = await repo.get_or_create_source("Controlled")
    owner = await repo.get_or_create_owner(123)
    for name, delta, message_id in (
        ("silent", 1, None), ("actual", 1, 999), ("recorded", 1, None), ("ancient", 5, None)
    ):
        saved = await repo.add_job(
            source_id=source.id, title=f"Vacante {name}", url=f"https://example.com/{name}",
            dedup_hash=name, published_at=NOW - timedelta(days=delta),
            notified=True, notification_message_id=message_id,
        )
        if name == "recorded":
            await repo.add_notification(owner.id, "nueva_oferta", job_id=saved.id)
    assert await repo.recover_legacy_baseline(NOW - timedelta(days=4), NOW) == 1
    pending = await repo.get_unnotified_jobs()
    assert [record.title for record in pending] == ["Vacante silent"]
    assert await repo.recover_legacy_baseline(NOW - timedelta(days=4), NOW) == 0


async def test_migration_upgrades_existing_database_without_marking_delivery(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'legacy.db'}")
    try:
        await db.create_tables()
        repository = Repository(db)
        source = await repository.get_or_create_source("Old")
        await repository.add_job(source_id=source.id, title="Inventario sin fecha",
                                 url="https://example.com/old", dedup_hash="old", notified=False)
        async with db.session() as session:
            await session.execute(text("ALTER TABLE jobs DROP COLUMN notification_eligible"))
            await session.commit()
        assert await run_migrations(db) == 5
        assert await run_migrations(db) == 0
        async with db.session() as session:
            result = await session.execute(text("SELECT notified, notification_eligible FROM jobs"))
            assert result.one() == (0, 0)
    finally:
        await db.close()


async def test_remote_country_metadata_survives_database_and_retry(repo):
    payload = job("remote-metadata")
    payload.raw_data = {"countries": ["Chile"], "remote_zone": "LATAM"}
    source = ControlledSource([payload])
    callback = AsyncMock(return_value=None)
    async with running(repo, [source], callback) as runner:
        await runner.initialize_baseline()
    source.jobs = []
    callback = AsyncMock(return_value=111)
    async with running(repo, [source], callback) as runner:
        await runner.initialize_baseline()
    assert callback.await_args.args[0].raw_data == payload.raw_data


async def test_promoted_listing_uses_updated_location_and_requirements(repo):
    payload = job("updated")
    payload.comuna = "Santiago"
    source = ControlledSource([payload])
    callback = AsyncMock(return_value=123)
    async with running(repo, [source], callback,
                       job_filter=lambda p: p.comuna == "Chillán") as runner:
        await runner.initialize_baseline()
        assert callback.await_count == 0
        updated = payload.model_copy(update={"comuna": "Chillán", "requirements": "Enseñanza media"})
        source.jobs = [updated]
        assert await runner.scan_and_dispatch_cycle() == 1
    assert callback.await_args.args[0].comuna == "Chillán"
    assert callback.await_args.args[0].requirements == "Enseñanza media"
