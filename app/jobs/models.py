"""Modelos Pydantic para intercambio, validación y normalización de ofertas laborales."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.database.models import ContractType, JobStatus, WorkModality, WorkSchedule


class JobPayload(BaseModel):
    """Carga útil de una oferta detectada desde cualquier fuente."""

    source_name: str
    external_id: str | None = None
    title: str = Field(..., min_length=2, max_length=500)
    company: str | None = Field(default=None, max_length=300)
    description: str | None = None
    location_raw: str | None = None
    region: str | None = None
    comuna: str | None = None
    modality: WorkModality = WorkModality.DESCONOCIDO
    contract_type: ContractType = ContractType.DESCONOCIDO
    schedule: WorkSchedule = WorkSchedule.DESCONOCIDO
    salary_min: int | None = None
    salary_max: int | None = None
    salary_type: str | None = None  # bruto, liquido, desconocido
    requirements: str | None = None
    experience_required: str | None = None
    education_required: str | None = None
    url: str = Field(..., max_length=1000)
    published_at: datetime | None = None
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    status: JobStatus = JobStatus.ACTIVA
    is_internship: bool = False
    dedup_hash: str | None = None
    raw_data: dict[str, Any] | None = None


class JobMatchCriteria(BaseModel):
    """Criterios para evaluar la compatibilidad de una vacante."""

    preferred_regions: list[str] = Field(default_factory=lambda: ["Ñuble"])
    preferred_comunas: list[str] = Field(default_factory=list)
    priority_comunas: list[str] = Field(default_factory=lambda: ["Chillán", "Chillán Viejo"])
    interest_areas: list[str] = Field(default_factory=list)
    interest_keywords: list[str] = Field(default_factory=list)
    exclude_internships: bool = True
    exclude_thesis: bool = True
    min_salary: int | None = None
    preferred_modality: str | None = None
    preferred_contract: str | None = None

    # Ponderaciones (0.0 a 1.0)
    weight_location: float = 0.25
    weight_skills: float = 0.25
    weight_experience: float = 0.15
    weight_education: float = 0.10
    weight_modality: float = 0.10
    weight_contract: float = 0.05
    weight_salary: float = 0.10


class JobMatchResult(BaseModel):
    """Resultado del cálculo de compatibilidad para una oferta."""

    score: int = Field(..., ge=0, le=100)
    is_excluded: bool = False
    exclusion_reason: str | None = None
    match_reasons: list[str] = Field(default_factory=list)
    missing_criteria: list[str] = Field(default_factory=list)
    breakdown: dict[str, float] = Field(default_factory=dict)
    summary: str
