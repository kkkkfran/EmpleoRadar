"""Pruebas unitarias para cálculo de compatibilidad (0-100) y filtros de exclusión."""

from app.database.models import ContractType, WorkModality
from app.jobs.matching import evaluate_job_match
from app.jobs.models import JobMatchCriteria, JobPayload
from app.jobs.ranking import rank_and_filter_jobs


def test_internship_excluded_by_default():
    criteria = JobMatchCriteria(exclude_internships=True)
    job = JobPayload(
        source_name="Test",
        title="Alumno en Práctica Desarrollo Web",
        url="https://test.cl/1",
        is_internship=True,
    )
    result = evaluate_job_match(job, criteria)
    assert result.is_excluded is True
    assert result.score == 0
    assert "práctica profesional" in result.exclusion_reason.lower()


def test_chillan_priority_gives_high_score():
    criteria = JobMatchCriteria(
        priority_comunas=["Chillán", "Chillán Viejo"],
        interest_keywords=["python", "backend"],
    )
    job = JobPayload(
        source_name="Test",
        title="Desarrollador Backend Python",
        description="Buscamos programador Python con base de datos SQL para Chillán.",
        comuna="Chillán",
        region="Ñuble",
        modality=WorkModality.PRESENCIAL,
        contract_type=ContractType.INDEFINIDO,
        url="https://test.cl/2",
    )
    result = evaluate_job_match(job, criteria)
    assert result.is_excluded is False
    assert result.score >= 70
    assert any("Chillán" in r for r in result.match_reasons)
    assert any("python" in r.lower() for r in result.match_reasons)


def test_remote_job_gives_high_location_score():
    criteria = JobMatchCriteria(
        preferred_regions=["Ñuble"],
        priority_comunas=["Chillán"],
    )
    job = JobPayload(
        source_name="Test",
        title="Ingeniero DevOps",
        description="Administración de infraestructura Cloud Docker y Linux.",
        modality=WorkModality.REMOTO,
        url="https://test.cl/3",
    )
    result = evaluate_job_match(job, criteria)
    assert result.is_excluded is False
    assert any("Remota" in r for r in result.match_reasons)


def test_ranking_and_filtering():
    criteria = JobMatchCriteria(priority_comunas=["Chillán"])
    jobs = [
        JobPayload(source_name="T", title="Práctica TI", url="http://1", is_internship=True),
        JobPayload(
            source_name="T", title="Desarrollador Python Chillán", comuna="Chillán", url="http://2"
        ),
        JobPayload(
            source_name="T",
            title="Vendedor Comercial Valparaíso",
            comuna="Valparaíso",
            region="Valparaíso",
            url="http://3",
        ),
    ]
    ranked = rank_and_filter_jobs(jobs, criteria, min_score=30)
    # Práctica excluida
    assert len(ranked) == 2
    # El de Chillán debe encabezar el ranking
    assert ranked[0][0].title == "Desarrollador Python Chillán"
    assert ranked[0][1].score > ranked[1][1].score
