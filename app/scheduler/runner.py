"""Planificador periódico de sondeo de ofertas con APScheduler."""

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

# Callback type for sending Discord notifications
NotificationCallback = Callable[[JobPayload, JobMatchResult, int], Coroutine[Any, Any, None]]


class JobSchedulerRunner:
    """Ejecutor de tareas en segundo plano para sondeo periódico de vacantes laborales."""

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

    async def start(self) -> None:
        """Inicia el planificador y la sesión HTTP."""
        if self._is_running:
            return

        self._session = aiohttp.ClientSession()
        self._is_running = True

        # Sincronizar fuentes con la base de datos
        await self.source_registry.sync_with_database()

        # Programar sondeo de fuentes activas
        active_sources = self.source_registry.get_active_sources()
        for src in active_sources:
            interval = max(5, src.poll_interval_minutes or self.poll_interval_minutes)
            self._scheduler.add_job(
                self.poll_source,
                "interval",
                minutes=interval,
                args=[src],
                id=f"poll_{src.name}",
                replace_existing=True,
            )
            logger.info("Programado sondeo para [%s] cada %d minutos.", src.name, interval)

        self._scheduler.start()
        logger.info("Planificador de sondeo iniciado correctamente.")

        # Ejecutar una primera pasada inicial en segundo plano
        asyncio.create_task(self.run_all_sources_now())

    async def stop(self) -> None:
        """Detiene el planificador y cierra conexiones."""
        if not self._is_running:
            return

        self._scheduler.shutdown(wait=False)
        if self._session and not self._session.closed:
            await self._session.close()

        self._is_running = False
        logger.info("Planificador de sondeo detenido.")

    async def run_all_sources_now(self, since_date: datetime | None = None) -> None:
        """Ejecuta un ciclo de sondeo inmediato sobre todas las fuentes activas."""
        cutoff = since_date or datetime(2026, 10, 13)
        sources = self.source_registry.get_active_sources()
        for src in sources:
            try:
                await self.poll_source(src, min_date=cutoff)
            except Exception as e:
                logger.error("Error durante sondeo de fuente %s: %s", src.name, e)

    async def poll_source(
        self,
        source: BaseJobSource,
        min_date: datetime | None = None,
    ) -> None:
        """Ejecuta el ciclo de extracción, deduplicación y notificación para una fuente."""
        if not self._session or self._session.closed:
            return

        cutoff_date = min_date or datetime(2026, 10, 13)

        # Verificar si el usuario pausó las notificaciones
        db_owner = await self.repo.get_owner(self.owner_id)
        if db_owner:
            db_prefs = await self.repo.get_or_create_preferences(db_owner.id)
            if db_prefs.is_paused:
                logger.info("Sondeo omitido temporalmente: notificaciones pausadas por el usuario.")
                return
            criteria = criteria_from_db_preferences(db_prefs)
        else:
            criteria = JobMatchCriteria()

        async with self.semaphore:
            start_time = time.time()
            jobs_found = 0
            duplicates_found = 0
            error_msg: str | None = None
            is_healthy = True

            try:
                raw_jobs = await source.fetch_jobs(self._session, criteria)
                jobs_found = len(raw_jobs)

                for job_payload in raw_jobs:
                    # Filtrar por fecha mínima (por defecto desde 13 de octubre)
                    pub_date = job_payload.published_at or datetime.now()
                    if pub_date < cutoff_date:
                        continue

                    # Comprobar huella de deduplicación
                    if not job_payload.dedup_hash:
                        from app.jobs.deduplication import compute_job_fingerprint

                        compute_job_fingerprint(job_payload)

                    db_source = await self.repo.get_or_create_source(source.name)
                    existing_job = await self.repo.job_exists_by_source_and_external_id(
                        db_source.id, str(job_payload.external_id)
                    )

                    if existing_job:
                        # Si ya existe en base de datos pero aún no fue notificada
                        if not existing_job.notified and self.notification_callback:
                            match_result = evaluate_job_match(job_payload, criteria)
                            try:
                                await self.notification_callback(
                                    job_payload, match_result, existing_job.id
                                )
                                await self.repo.mark_job_notified(existing_job.id)
                                await asyncio.sleep(0.3)
                            except Exception as notif_err:
                                logger.error("Error al despachar notificación: %s", notif_err)
                        duplicates_found += 1
                        continue

                    # Guardar la nueva vacante
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

                    # Evaluar compatibilidad con el perfil
                    match_result = evaluate_job_match(job_payload, criteria)

                    # Despachar notificación
                    if self.notification_callback:
                        try:
                            await self.notification_callback(
                                job_payload, match_result, saved_job.id
                            )
                            await self.repo.mark_job_notified(saved_job.id)
                            await asyncio.sleep(0.3)
                        except Exception as notif_err:
                            logger.error(
                                "Error al despachar notificación a Discord: %s", notif_err
                            )

            except Exception as e:
                is_healthy = False
                error_msg = str(e)
                logger.error("Fallo durante sondeo de [%s]: %s", source.name, e)

            # Registrar salud de la fuente en base de datos
            elapsed_ms = int((time.time() - start_time) * 1000)
            db_source = await self.repo.get_or_create_source(source.name)
            await self.repo.update_source_health(
                source_id=db_source.id,
                is_healthy=is_healthy,
                response_time_ms=elapsed_ms,
                jobs_found=jobs_found,
                duplicates_found=duplicates_found,
                error_message=error_msg,
            )
