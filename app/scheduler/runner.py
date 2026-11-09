"""Sondeo concurrente, recuperación acotada y cola persistente de avisos."""

from __future__ import annotations

import ast
import asyncio
import json
import logging
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.database.models import Job
from app.database.repository import Repository
from app.jobs.deduplication import compute_job_fingerprint
from app.jobs.matching import evaluate_job_match
from app.jobs.models import JobMatchCriteria, JobMatchResult, JobPayload
from app.profile.preferences import criteria_from_db_preferences
from app.sources.base import BaseJobSource
from app.sources.registry import SourceRegistry

logger = logging.getLogger(__name__)
NotificationCallback = Callable[[JobPayload, JobMatchResult, int], Coroutine[Any, Any, int | None]]


def _utc_naive(value: datetime) -> datetime:
    """La base SQLite guarda fechas UTC sin offset; nunca usar la zona del host."""
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass
class _SourceResult:
    source: BaseJobSource
    jobs: list[JobPayload]
    elapsed_ms: int
    error: str | None = None


class JobSchedulerRunner:
    """Recupera los últimos días y entrega cada lote sin esperar a portales lentos."""

    def __init__(
        self,
        repository: Repository,
        source_registry: SourceRegistry,
        owner_id: int,
        notification_callback: NotificationCallback | None = None,
        poll_interval_minutes: int = 2,
        max_concurrent_requests: int = 3,
        recovery_days: int = 4,
        request_timeout_seconds: int = 30,
        source_timeout_seconds: float = 180,
        job_filter: Callable[[JobPayload], bool] | None = None,
        notification_delay_seconds: float = 0.8,
    ) -> None:
        self.repo = repository
        self.source_registry = source_registry
        self.owner_id = owner_id
        self.notification_callback = notification_callback
        self.poll_interval_minutes = poll_interval_minutes
        self.recovery_days = recovery_days
        self.request_timeout_seconds = request_timeout_seconds
        self.source_timeout_seconds = source_timeout_seconds
        self.job_filter = job_filter
        self.notification_delay_seconds = notification_delay_seconds
        self.semaphore = asyncio.Semaphore(max_concurrent_requests)
        self._scheduler = AsyncIOScheduler(timezone="UTC")
        self._session: aiohttp.ClientSession | None = None
        self._is_running = False
        self._polling_lock = asyncio.Lock()
        self._baseline_ready = False
        self._initialized_sources: set[str] = set()
        self._cycle_tasks: set[asyncio.Task] = set()
        self.last_cycle_started_at: datetime | None = None
        self.last_cycle_completed_at: datetime | None = None

    async def initialize_baseline(self) -> int:
        """Recupera publicaciones de los últimos días; no simula avisos enviados."""
        if self._baseline_ready:
            return 0
        now = _now()
        repaired = await self.repo.recover_legacy_baseline(
            now - timedelta(days=self.recovery_days), now
        )
        if repaired:
            logger.info("Recuperadas %d marcas silenciosas antiguas sin evidencia de envío.", repaired)
        count = await self.scan_and_dispatch_cycle()
        logger.info("Recuperación inicial: %d avisos enviados; ventana de %d días.", count, self.recovery_days)
        return count

    async def start(self) -> None:
        """Inicializa recursos. El cliente lo invoca una vez que Discord está listo."""
        if self._is_running:
            return
        await self.source_registry.sync_with_database()
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.request_timeout_seconds)
        )
        self._scheduler.add_job(
            self.scan_and_dispatch_cycle,
            "interval",
            minutes=max(1, self.poll_interval_minutes),
            id="unified_job_scanner",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
        )
        self._scheduler.start()
        self._is_running = True
        logger.info("Sondeo iniciado cada %d minutos.", self.poll_interval_minutes)

    async def stop(self) -> None:
        """Cancela consultas pendientes antes de cerrar HTTP y la base de datos."""
        if not self._is_running:
            return
        self._is_running = False
        self._scheduler.shutdown(wait=False)
        tasks = [task for task in self._cycle_tasks if task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self._session and not self._session.closed:
            await self._session.close()
        logger.info("Sondeo detenido.")

    @staticmethod
    def get_job_datetime(job: JobPayload) -> datetime:
        return _utc_naive(job.published_at or job.detected_at)

    async def poll_source(self, source: BaseJobSource, min_date: datetime | None = None) -> None:
        await self._dispatch_jobs_for_sources([source], since_date=min_date)

    async def run_all_sources_now(self, since_date: datetime | None = None) -> int:
        return await self.scan_and_dispatch_cycle(since_date=since_date)

    async def scan_and_dispatch_cycle(self, since_date: datetime | None = None) -> int:
        await self.source_registry.sync_with_database()
        return await self._dispatch_jobs_for_sources(
            self.source_registry.get_active_sources(), since_date=since_date
        )

    async def _collect_source(self, source: BaseJobSource, criteria: JobMatchCriteria) -> _SourceResult:
        async with self.semaphore:
            started = time.monotonic()
            source.timeout_seconds = self.request_timeout_seconds
            source.recovery_days = self.recovery_days
            try:
                jobs = await asyncio.wait_for(
                    source.fetch_jobs(self._session, criteria), timeout=self.source_timeout_seconds
                )
                # Algunos conectores devuelven resultados parciales tras registrar un error.
                error = source.last_error
                return _SourceResult(source, jobs, int((time.monotonic() - started) * 1000), error)
            except Exception as exc:
                error = (
                    f"Tiempo máximo de consulta excedido ({self.source_timeout_seconds:g}s)"
                    if isinstance(exc, TimeoutError) else str(exc)
                )
                source.record_error(error)
                return _SourceResult(source, [], int((time.monotonic() - started) * 1000), error)

    async def _dispatch_jobs_for_sources(
        self,
        sources: list[BaseJobSource],
        since_date: datetime | None = None,
    ) -> int:
        if not self._session or self._session.closed:
            return 0
        if self._polling_lock.locked():
            logger.info("Ya hay un ciclo en ejecución; se omite la invocación concurrente.")
            return 0
        async with self._polling_lock:
            task = asyncio.current_task()
            if task:
                self._cycle_tasks.add(task)
            fetch_tasks: list[asyncio.Task] = []
            try:
                now = _now()
                self.last_cycle_started_at = now
                cutoff = now - timedelta(days=self.recovery_days)
                if since_date is not None:
                    cutoff = max(cutoff, _utc_naive(since_date))
                owner = await self.repo.get_owner(self.owner_id)
                criteria = JobMatchCriteria()
                if owner:
                    preferences = await self.repo.get_or_create_preferences(owner.id)
                    if preferences.is_paused:
                        logger.info("Avisos pausados por el usuario.")
                        self.last_cycle_completed_at = _now()
                        return 0
                    criteria = criteria_from_db_preferences(preferences)

                attempted_ids: set[int] = set()
                fetch_tasks = [asyncio.create_task(self._collect_source(s, criteria)) for s in sources]
                dispatched = await self._dispatch_pending(
                    criteria, cutoff, now, attempted_ids, include_undated=since_date is None
                )
                for completed in asyncio.as_completed(fetch_tasks):
                    result = await completed
                    source = result.source
                    db_source = await self.repo.get_or_create_source(source.name)
                    await self.repo.update_source_health(
                        db_source.id,
                        is_healthy=result.error is None,
                        response_time_ms=result.elapsed_ms,
                        jobs_found=len(result.jobs),
                        error_message=result.error,
                    )
                    initial_inventory = source.name not in self._initialized_sources
                    await self._store_jobs(
                        result.jobs, cutoff, _now(),
                        allow_undated=not initial_inventory and since_date is None,
                    )
                    if result.error is None:
                        self._initialized_sources.add(source.name)
                    else:
                        logger.warning("[%s] Consulta incompleta: %s", source.name, result.error)
                    dispatched += await self._dispatch_pending(
                        criteria, cutoff, _now(), attempted_ids, include_undated=since_date is None
                    )
                self._baseline_ready = all(
                    s.name in self._initialized_sources for s in self.source_registry.get_active_sources()
                )
                self.last_cycle_completed_at = _now()
                logger.info("Ciclo completado: %d avisos enviados.", dispatched)
                return dispatched
            finally:
                for fetch_task in fetch_tasks:
                    if not fetch_task.done():
                        fetch_task.cancel()
                if fetch_tasks:
                    await asyncio.gather(*fetch_tasks, return_exceptions=True)
                if task:
                    self._cycle_tasks.discard(task)

    async def _store_jobs(
        self, jobs: list[JobPayload], cutoff: datetime, now: datetime, *, allow_undated: bool
    ) -> None:
        # Priorizar fecha comprobable si dos resultados describen la misma vacante.
        for payload in sorted(jobs, key=lambda j: (j.published_at is None, self.get_job_datetime(j))):
            if payload.published_at is not None:
                payload.published_at = _utc_naive(payload.published_at)
                if not cutoff <= payload.published_at <= now:
                    continue
            if payload.status != "activa":
                continue
            eligible = payload.published_at is not None or allow_undated
            if self.job_filter and not self.job_filter(payload):
                eligible = False
            if not payload.dedup_hash:
                compute_job_fingerprint(payload)
            source = await self.repo.get_or_create_source(payload.source_name)
            existing = None
            if payload.external_id is not None:
                existing = await self.repo.job_exists_by_source_and_external_id(source.id, str(payload.external_id))
            if existing is None:
                existing = await self.repo.get_job_by_hash(payload.dedup_hash)
            if existing is None:
                existing = await self.repo.find_semantic_duplicate(payload.title, payload.comuna, payload.company)
            if existing is not None:
                if existing.notified or existing.user_decision != "pending":
                    continue
                if eligible and payload.published_at is not None and not existing.notification_eligible:
                    # Una fecha publicada posteriormente sí permite recuperar el inventario.
                    updates = payload.model_dump(exclude={
                        "source_name", "external_id", "location_raw", "raw_data",
                        "detected_at", "dedup_hash",
                    })
                    for field in ("modality", "contract_type", "schedule", "status"):
                        updates[field] = updates[field].value
                    await self.repo.update_job(
                        existing.id, **updates, notification_eligible=True,
                        location=payload.location_raw,
                        raw_data=json.dumps(payload.raw_data or {}, ensure_ascii=False, default=str),
                    )
                continue
            values = payload.model_dump(exclude={"source_name", "location_raw", "raw_data", "detected_at"})
            for field in ("modality", "contract_type", "schedule", "status"):
                values[field] = values[field].value
            await self.repo.add_job(
                **values,
                source_id=source.id,
                location=payload.location_raw,
                detected_at=now,
                notification_eligible=eligible,
                raw_data=json.dumps(payload.raw_data or {}, ensure_ascii=False, default=str),
            )
            await self.repo.increment_source_jobs_count(source.id)

    @staticmethod
    def _payload_from_job(job: Job) -> JobPayload:
        values = {
            name: getattr(job, name)
            for name in JobPayload.model_fields
            if name not in {"source_name", "location_raw", "raw_data"}
        }
        raw_data = {}
        if job.raw_data:
            try:
                raw_data = json.loads(job.raw_data)
            except (ValueError, TypeError):
                try:
                    raw_data = ast.literal_eval(job.raw_data)
                except (ValueError, SyntaxError, TypeError):
                    raw_data = {}
        return JobPayload(
            **values, source_name=job.source.name, location_raw=job.location,
            raw_data=raw_data if isinstance(raw_data, dict) else {},
        )

    async def _dispatch_pending(
        self,
        criteria: JobMatchCriteria,
        cutoff: datetime,
        now: datetime,
        attempted_ids: set[int],
        *,
        include_undated: bool,
    ) -> int:
        if not self.notification_callback:
            return 0
        dispatched = 0
        pending = await self.repo.get_unnotified_jobs(cutoff, include_undated=include_undated)
        for job in pending:
            owner = await self.repo.get_owner(self.owner_id)
            if owner and (await self.repo.get_or_create_preferences(owner.id)).is_paused:
                logger.info("Envío interrumpido: el usuario pausó las notificaciones.")
                break
            if job.id in attempted_ids:
                continue
            if job.published_at and _utc_naive(job.published_at) > now:
                continue
            attempted_ids.add(job.id)
            payload = self._payload_from_job(job)
            if self.job_filter and not self.job_filter(payload):
                await self.repo.update_job(job.id, notification_eligible=False)
                continue
            match = evaluate_job_match(payload, criteria)
            if match.is_excluded:
                continue
            try:
                message_id = await self.notification_callback(payload, match, job.id)
                if message_id:
                    await self.repo.mark_job_notified(job.id, message_id)
                    dispatched += 1
                    if self.notification_delay_seconds:
                        await asyncio.sleep(self.notification_delay_seconds)
            except Exception:
                logger.exception("El aviso #%d permanece pendiente para reintento.", job.id)
        return dispatched
