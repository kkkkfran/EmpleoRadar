"""Prueba de integración End-to-End del ciclo completo de EmpleoRadar con fuente simulada."""

import pytest

from app.applications.service import ApplicationService
from app.database.migrations.runner import run_migrations
from app.database.models import ApplicationStatus
from app.database.repository import Database, Repository
from app.jobs.models import JobPayload
from app.profile.cv_storage import CVStorage
from app.profile.service import ProfileService
from app.scheduler.runner import JobSchedulerRunner
from app.sources.base import BaseJobSource
from app.sources.registry import SourceRegistry


class MockJobSource(BaseJobSource):
    """Fuente simulada con respuestas controladas para pruebas de integración."""

    def __init__(self, jobs_to_return):
        super().__init__(
            name="MockSource",
            base_url="https://mock.local",
            source_type="rss",
            poll_interval_minutes=15,
        )
        self.jobs_to_return = jobs_to_return

    async def fetch_jobs(self, session, criteria=None):
        return self.jobs_to_return


@pytest.mark.asyncio
async def test_full_pipeline_detection_dedup_and_application(tmp_path):
    db = Database("sqlite+aiosqlite:///:memory:")
    await db.create_tables()
    await run_migrations(db)

    repo = Repository(db)
    storage = CVStorage(tmp_path / "cvs")
    profile_service = ProfileService(repo, storage)
    app_service = ApplicationService(repo, profile_service, require_confirmation=True)

    # Configurar usuario propietario con perfil en Chillán
    owner = await repo.get_or_create_owner(discord_id=987654321, username="test_owner")
    await repo.update_profile(
        owner.id,
        education="Ingeniería en Informática",
        salary_expectation_min=1_000_000,
    )
    await repo.update_preferences(
        owner.id,
        preferred_regions='["Ñuble"]',
        priority_comunas='["Chillán", "Chillán Viejo"]',
        exclude_internships=True,
        min_score_notify=30,
    )

    notified_jobs = []

    async def mock_notify_callback(job, match_result, job_id):
        notified_jobs.append((job, match_result, job_id))

    # Crear oferta de prueba
    sample_job = JobPayload(
        source_name="MockSource",
        external_id="mock_job_001",
        title="Desarrollador Python / Backend",
        company="Ñuble Software SpA",
        description="Desarrollo de APIs REST en Python y SQL. Ubicación Chillán.",
        comuna="Chillán",
        region="Ñuble",
        url="https://mock.local/oferta/001",
    )

    source_registry = SourceRegistry(repo)
    mock_src = MockJobSource([sample_job])
    source_registry._sources["MockSource"] = mock_src

    runner = JobSchedulerRunner(
        repository=repo,
        source_registry=source_registry,
        owner_id=987654321,
        notification_callback=mock_notify_callback,
    )

    # Iniciar runner
    await runner.start()

    # Ejecutar ciclo de sondeo
    await runner.poll_source(mock_src)

    # 1. Comprobar que la vacante se guardó en BD y se notificó
    stats = await repo.get_job_stats()
    assert stats["total"] == 1
    assert len(notified_jobs) == 1
    job_payload, match_res, job_id = notified_jobs[0]
    assert job_payload.title == "Desarrollador Python / Backend"
    assert match_res.score >= 50

    # 2. Segundo ciclo: Deduplicación debe evitar duplicar la oferta o reenviar notificación
    await runner.poll_source(mock_src)
    stats_after = await repo.get_job_stats()
    assert stats_after["total"] == 1  # No se duplicó
    assert len(notified_jobs) == 1  # No se volvió a notificar

    # 3. Preparar postulación para la oferta detectada
    draft = await app_service.prepare_application(owner.id, job_id)
    assert draft.job_title == "Desarrollador Python / Backend"
    assert draft.application_id is not None

    # 4. Responder una pregunta en el borrador
    await app_service.save_answer(
        draft.application_id,
        "¿Cuáles son sus pretensiones de renta?",
        "$1.200.000 líquidos.",
    )

    # 5. Tramitar postulación confirmada
    submit_res = await app_service.submit_application(
        owner_id=owner.id,
        application_id=draft.application_id,
        confirmed_by_user=True,
    )
    assert submit_res.success is True
    assert submit_res.status == ApplicationStatus.REQUIERE_INTERVENCION

    # 6. Historial de postulaciones
    history = await app_service.get_history(owner.id)
    assert len(history) == 1
    assert history[0].job_id == job_id

    # Detener runner y cerrar BD
    await runner.stop()
    await db.close()
