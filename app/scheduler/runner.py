"""Planificador periódico continuo y despacho unificado de ofertas laborales."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import Any

import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.database.repository import Repository
from app.jobs.matching import evaluate_job_match
from app.jobs.models import JobMatchCriteria, JobMatchResult, JobPayload
from app.profile.preferences import criteria_from_db_preferences
from app.sources.base import BaseJobSource
from app.sources.registry import SourceRegistry

logger = logging.getLogger(__name__)

# Callback para enviar notificaciones a Discord (retorna True si se envió mensaje)
NotificationCallback = Callable[[JobPayload, JobMatchResult, int], Coroutine[Any, Any, bool]]


class JobSchedulerRunner:
    """Ejecutor de tareas en segundo plano para sondeo periódico continuo y despacho ordenado."""

    def __init__(
        self,
        repository: Repository,
        source_registry: SourceRegistry,
        owner_id: int,
        notification_callback: NotificationCallback | None = None,
        poll_interval_minutes: int = 15,
        max_concurrent_requests: int = 3,
    ) -> None:
        self.repo = repository
        self.source_registry = source_registry
        self.owner_id = owner_id
        self.notification_callback = notification_callback
        self.poll_interval_minutes = poll_interval_minutes
        self.semaphore = asyncio.Semaphore(max_concurrent_requests)

        self._scheduler = AsyncIOScheduler()
        self._session: aiohttp.ClientSession | None = None
        self._is_running = False
        self._polling_lock = asyncio.Lock()

    async def start(self) -> None:
        """Inicia el planificador daemon y la sesión HTTP."""
        if self._is_running:
            return

        self._session = aiohttp.ClientSession()
        self._is_running = True

        # Sincronizar fuentes con la base de datos
        await self.source_registry.sync_with_database()

        # Programar sondeo periódico continuo unificado
        interval = max(2, self.poll_interval_minutes)
        self._scheduler.add_job(
            self.scan_and_dispatch_cycle,
            "interval",
            minutes=interval,
            id="unified_job_scanner",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info(
            "Planificador de sondeo continuo iniciado (frecuencia: cada %d minutos).",
            interval,
        )

    async def stop(self) -> None:
        """Detiene el planificador y cierra conexiones."""
        if not self._is_running:
            return

        self._scheduler.shutdown(wait=False)
        if self._session and not self._session.closed:
            await self._session.close()

        self._is_running = False
        logger.info("Planificador de sondeo detenido.")

    @staticmethod
    def get_job_datetime(job: JobPayload) -> datetime:
        """Obtiene la fecha de ordenamiento cronológico de forma homogénea (naive)."""
        dt = job.published_at or job.detected_at or datetime.now()
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt

    async def poll_source(
        self,
        source: BaseJobSource,
        min_date: datetime | None = None,
    ) -> None:
        """Ejecuta el ciclo de extracción para una fuente específica."""
        await self._dispatch_jobs_for_sources([source], since_date=min_date)

    async def run_all_sources_now(self, since_date: datetime | None = None) -> int:
        """Alias para ejecutar un ciclo de escaneo y despacho inmediato."""
        return await self.scan_and_dispatch_cycle(since_date=since_date)

    async def scan_and_dispatch_cycle(self, since_date: datetime | None = None) -> int:
        """Ejecuta el ciclo unificado sobre todas las fuentes activas."""
        sources = self.source_registry.get_active_sources()
        return await self._dispatch_jobs_for_sources(sources, since_date=since_date)

    async def _dispatch_jobs_for_sources(
        self,
        sources: list[BaseJobSource],
        since_date: datetime | None = None,
    ) -> int:
        """Ciclo unificado de recolección, deduplicación, ordenamiento cronológico y despacho.

        1. Consulta las fuentes suministradas (todas o específicas).
        2. Unifica las ofertas en una sola colección independiente de la fuente.
        3. Deduplica en memoria.
        4. Ordena ASCENDENTEMENTE (de la más antigua a la más nueva) para que en Discord
           la más reciente quede abajo del todo.
        5. Inserta y despacha directamente a Discord con delay anti rate-limit.
        """
        if not self._session or self._session.closed:
            return 0

        if self._polling_lock.locked():
            logger.warning(
                "Ciclo de escaneo actualmente en ejecución. Omitiendo invocación concurrente."
            )
            return 0

        async with self._polling_lock:
            cutoff_date = since_date or datetime(2026, 10, 13)

            # Verificar preferencias de usuario
            db_owner = await self.repo.get_owner(self.owner_id)
            if db_owner:
                db_prefs = await self.repo.get_or_create_preferences(db_owner.id)
                if db_prefs.is_paused:
                    logger.info("Sondeo omitido temporalmente: notificaciones pausadas por el usuario.")
                    return 0
                criteria = criteria_from_db_preferences(db_prefs)
            else:
                criteria = JobMatchCriteria()

            logger.info("Iniciando ciclo unificado de recolección en %d fuentes...", len(sources))

            all_raw_jobs: list[JobPayload] = []

            # 1. Recolección desde cada fuente activa
            for source in sources:
                async with self.semaphore:
                    start_t = time.time()
                    try:
                        jobs = await source.fetch_jobs(self._session, criteria)
                        all_raw_jobs.extend(jobs)
                        elapsed_ms = int((time.time() - start_t) * 1000)
                        db_source = await self.repo.get_or_create_source(source.name)
                        await self.repo.update_source_health(
                            source_id=db_source.id,
                            is_healthy=True,
                            response_time_ms=elapsed_ms,
                            jobs_found=len(jobs),
                        )
                        logger.info("[%s] recolectó %d ofertas.", source.name, len(jobs))
                    except Exception as e:
                        elapsed_ms = int((time.time() - start_t) * 1000)
                        logger.error("Error consultando [%s]: %s", source.name, e)
                        db_source = await self.repo.get_or_create_source(source.name)
                        await self.repo.update_source_health(
                            source_id=db_source.id,
                            is_healthy=False,
                            response_time_ms=elapsed_ms,
                            error_message=str(e),
                        )

            logger.info(
                "Total recolectado entre fuentes: %d ofertas.", len(all_raw_jobs)
            )

            # 2. Filtrar por fecha mínima (por defecto 13 de octubre)
            valid_jobs: list[JobPayload] = []
            for j in all_raw_jobs:
                if self.get_job_datetime(j) >= cutoff_date:
                    valid_jobs.append(j)

            # 3. Deduplicación en memoria de la colección unificada
            unique_jobs: list[JobPayload] = []
            seen_hashes: set[str] = set()
            for j in valid_jobs:
                if not j.dedup_hash:
                    from app.jobs.deduplication import compute_job_fingerprint

                    compute_job_fingerprint(j)

                if j.dedup_hash in seen_hashes:
                    continue
                seen_hashes.add(j.dedup_hash)
                unique_jobs.append(j)

            # 4. ORDENAMIENTO GLOBAL ASCENDENTE (de la más antigua a la más nueva)
            # La fuente es irrelevante; la prioridad absoluta es la fecha real
            unique_jobs.sort(key=self.get_job_datetime, reverse=False)

            logger.info(
                "Ofertas únicas filtradas a despachar en orden cronológico ascendente: %d",
                len(unique_jobs),
            )

            # 5. Inserción y despacho directo a Discord
            dispatched_count = 0
            for job_payload in unique_jobs:
                db_source = await self.repo.get_or_create_source(job_payload.source_name)
                existing_job = await self.repo.job_exists_by_source_and_external_id(
                    db_source.id, str(job_payload.external_id)
                )

                if not existing_job:
                    existing_job = await self.repo.get_job_by_hash(job_payload.dedup_hash)

                if existing_job:
                    # Si ya existe en base de datos pero estaba pendiente de notificar
                    if not existing_job.notified and self.notification_callback:
                        match_result = evaluate_job_match(job_payload, criteria)
                        try:
                            sent = await self.notification_callback(
                                job_payload, match_result, existing_job.id
                            )
                            await self.repo.mark_job_notified(existing_job.id)
                            if sent:
                                dispatched_count += 1
                                await asyncio.sleep(0.8)  # Delay prudente anti rate-limit
                        except Exception as notif_err:
                            logger.error(
                                "Error al despachar oferta pendiente #%d: %s",
                                existing_job.id,
                                notif_err,
                            )
                    continue

                # Oferta NUEVA: Insertar de inmediato en la base de datos
                saved_job = await self.repo.add_job(
                    source_id=db_source.id,
                    external_id=job_payload.external_id,
                    title=job_payload.title,
                    company=job_payload.company,
                    description=job_payload.description,
                    location=job_payload.location_raw,
                    region=job_payload.region,
                    comuna=job_payload.comuna,
                    modality=job_payload.modality.value,
                    contract_type=job_payload.contract_type.value,
                    schedule=job_payload.schedule.value,
                    salary_min=job_payload.salary_min,
                    salary_max=job_payload.salary_max,
                    salary_type=job_payload.salary_type,
                    requirements=job_payload.requirements,
                    experience_required=job_payload.experience_required,
                    education_required=job_payload.education_required,
                    url=job_payload.url,
                    published_at=job_payload.published_at,
                    is_internship=job_payload.is_internship,
                    dedup_hash=job_payload.dedup_hash,
                    raw_data=str(job_payload.raw_data or {}),
                )
                await self.repo.increment_source_jobs_count(db_source.id, 1)

                # Despacho en tiempo real al canal correspondiente
                if self.notification_callback:
                    match_result = evaluate_job_match(job_payload, criteria)
                    try:
                        sent = await self.notification_callback(
                            job_payload, match_result, saved_job.id
                        )
                        await self.repo.mark_job_notified(saved_job.id)
                        if sent:
                            dispatched_count += 1
                            await asyncio.sleep(0.8)  # Delay prudente de 800ms
                    except Exception as notif_err:
                        logger.error(
                            "Error al despachar notificación a Discord: %s", notif_err
                        )

            logger.info(
                "Ciclo de escaneo finalizado. Nuevas notificaciones enviadas a Discord: %d",
                dispatched_count,
            )
            return dispatched_count
