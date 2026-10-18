"""Pruebas unitarias para la capa de base de datos, modelos, repositorio y migraciones."""

import pytest

from app.database.migrations.runner import run_migrations
from app.database.models import ApplicationStatus
from app.database.repository import Database, Repository


@pytest.fixture
async def test_db():
    """Inicializa una base de datos en memoria para pruebas."""
    db = Database("sqlite+aiosqlite:///:memory:")
    await db.create_tables()
    await run_migrations(db)
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_owner_and_profile_crud(test_db):
    repo = Repository(test_db)

    # 1. Crear propietario
    owner = await repo.get_or_create_owner(discord_id=123456789, username="usuario_nuble")
    assert owner.id is not None
    assert owner.discord_id == 123456789

    # 2. Perfil
    profile = await repo.get_or_create_profile(owner.id)
    assert profile.owner_id == owner.id

    updated_profile = await repo.update_profile(
        owner.id,
        education="Ingeniería en Informática",
        availability="Inmediata",
        salary_expectation_min=1_200_000,
    )
    assert updated_profile.education == "Ingeniería en Informática"
    assert updated_profile.salary_expectation_min == 1_200_000

    # 3. Preferencias
    prefs = await repo.get_or_create_preferences(owner.id)
    assert prefs.exclude_internships is True
    await repo.update_preferences(owner.id, min_salary=1_000_000, is_paused=True)
    refreshed_prefs = await repo.get_or_create_preferences(owner.id)
    assert refreshed_prefs.min_salary == 1_000_000
    assert refreshed_prefs.is_paused is True


@pytest.mark.asyncio
async def test_jobs_deduplication_and_search(test_db):
    repo = Repository(test_db)
    source = await repo.get_or_create_source(name="ChileTrabajos")

    # Agregar job 1
    job1 = await repo.add_job(
        source_id=source.id,
        title="Desarrollador Python Chillán",
        company="AgroTI Ñuble",
        description="Desarrollo de microservicios con PostgreSQL y FastAPI.",
        comuna="Chillán",
        region="Ñuble",
        url="https://chiletrabajos.cl/oferta/1",
        dedup_hash="hash_test_123",
    )
    assert job1.id is not None

    # Verificar que existe por hash
    assert await repo.job_exists_by_hash("hash_test_123") is True
    assert await repo.job_exists_by_hash("otro_hash") is False

    # Búsqueda por texto
    results = await repo.search_jobs("FastAPI")
    assert len(results) == 1
    assert results[0].title == "Desarrollador Python Chillán"

    # Estadísticas
    stats = await repo.get_job_stats()
    assert stats["total"] == 1


@pytest.mark.asyncio
async def test_applications_lifecycle(test_db):
    repo = Repository(test_db)
    owner = await repo.get_or_create_owner(discord_id=123456789)
    source = await repo.get_or_create_source(name="ChileTrabajos")
    job = await repo.add_job(
        source_id=source.id,
        title="Soporte Técnico Informático",
        company="Hospital de San Carlos",
        url="https://chiletrabajos.cl/oferta/99",
        dedup_hash="hash_hosp_sancarlos",
    )

    # Crear postulación
    app = await repo.create_application(owner_id=owner.id, job_id=job.id)
    assert app.status == ApplicationStatus.DETECTADA.value

    # Actualizar estado
    await repo.update_application_status(
        application_id=app.id,
        status=ApplicationStatus.EN_PREPARACION.value,
        detail="Respuestas en borrador",
    )
    updated_app = await repo.get_application(app.id)
    assert updated_app.status == ApplicationStatus.EN_PREPARACION.value

    # Guardar respuesta
    answer = await repo.save_application_answer(
        application_id=app.id,
        question="¿Posee experiencia en soporte?",
        answer="Sí, 2 años en mantención de equipos y redes.",
    )
    assert answer.id is not None
    answers = await repo.get_application_answers(app.id)
    assert len(answers) == 1
    assert answers[0].answer == "Sí, 2 años en mantención de equipos y redes."
