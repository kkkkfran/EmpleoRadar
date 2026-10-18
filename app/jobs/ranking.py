"""Clasificación, filtrado y ordenamiento de oportunidades laborales."""

from __future__ import annotations

from app.jobs.matching import evaluate_job_match
from app.jobs.models import JobMatchCriteria, JobMatchResult, JobPayload


def rank_and_filter_jobs(
    jobs: list[JobPayload],
    criteria: JobMatchCriteria,
    min_score: int = 30,
) -> list[tuple[JobPayload, JobMatchResult]]:
    """Evalúa, filtra y clasifica una lista de ofertas de mayor a menor compatibilidad.

    Descarta ofertas excluidas (como prácticas) o con puntaje inferior al umbral.
    """
    ranked: list[tuple[JobPayload, JobMatchResult]] = []

    for job in jobs:
        result = evaluate_job_match(job, criteria)
        if result.is_excluded:
            continue
        if result.score >= min_score:
            ranked.append((job, result))

    # Ordenar por puntaje descendente, y luego por fecha de detección más reciente
    ranked.sort(key=lambda item: (item[1].score, item[0].detected_at), reverse=True)
    return ranked
