"""Pruebas unitarias para el servicio de postulaciones y asistente de respuestas."""

import pytest

from app.applications.answers import match_answer_for_question
from app.applications.service import ApplicationService
from app.database.migrations.runner import run_migrations
from app.database.models import ApplicationStatus
from app.database.repository import Database, Repository
from app.profile.cv_storage import CVStorage
from app.profile.service import ProfileService


@pytest.fixture
async def app_setup(tmp_path):
    db = Database("sqlite+aiosqlite:///:memory:")
    await db.create_tables()
    await run_migrations(db)
    repo = Repository(db)
    storage = CVStorage(tmp_path)
    profile_service = ProfileService(repo, storage)
    app_service = ApplicationService(repo, profile_service, require_confirmation=True)
    yield repo, profile_service, app_service
    await db.close()


@pytest.mark.asyncio
async def test_answers_matcher_uses_verified_profile_data(app_setup):
    repo, profile_service, _ = app_setup
    owner = await repo.get_or_create_owner(12345)
    await repo.update_profile(
        owner.id,
        salary_expectation_min=1_300_000,
        availability="Inmediata",
        drivers_license="Clase B",
        own_transport=True,
    )
    profile = await profile_service.get_profile(owner.id)

    # Renta
    ans, src, verified = match_answer_for_question(
        "¿Cuáles son sus pretensiones de renta?", profile, []
    )
    assert "1,300,000" in ans
    assert verified is True

    # Disponibilidad
    ans, src, verified = match_answer_for_question("¿Disponibilidad para ingresar?", profile, [])
    assert "Inmediata" in ans

    # Licencia
    ans, src, verified = match_answer_for_question("¿Cuenta con licencia clase B?", profile, [])
    assert "Clase B" in ans

    # Pregunta desconocida no inventa
    ans, src, verified = match_answer_for_question("¿Experiencia en SAP Business One?", profile, [])
    assert verified is False
    assert ans.startswith("(")


@pytest.mark.asyncio
async def test_draft_and_submission_with_confirmation(app_setup):
    repo, _, app_service = app_setup
    owner = await repo.get_or_create_owner(12345)
    source = await repo.get_or_create_source("ChileTrabajos")
    job = await repo.add_job(
        source_id=source.id,
        title="Desarrollador Full Stack",
        company="Startup Chillán",
        url="https://chiletrabajos.cl/oferta/55",
        dedup_hash="hash_55",
    )

    # 1. Preparar borrador
    draft = await app_service.prepare_application(owner.id, job.id)
    assert draft.job_title == "Desarrollador Full Stack"
    assert len(draft.questions) > 0

    # 2. Intento de envío sin confirmación explícita es rechazado
    res = await app_service.submit_application(
        owner.id, draft.application_id, confirmed_by_user=False
    )
    assert res.success is False
    assert res.status == ApplicationStatus.PENDIENTE_CONFIRMACION

    # 3. Envío con confirmación explícita
    res = await app_service.submit_application(
        owner.id, draft.application_id, confirmed_by_user=True
    )
    assert res.success is True
    assert res.portal_url == job.url
    assert "chiletrabajos.cl" in res.manual_instructions
