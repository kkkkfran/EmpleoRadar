"""Gestión y valores por defecto de preferencias del candidato."""

from __future__ import annotations

import json
from typing import Any

from app.jobs.models import JobMatchCriteria
from app.jobs.regions_data import COMUNAS_PRIORITARIAS_DEFAULT

DEFAULT_AREAS: list[str] = [
    "Ingeniería en Informática",
    "Desarrollo backend",
    "Desarrollo full stack",
    "Desarrollo web",
    "Python",
    "JavaScript y TypeScript",
    "Node.js",
    "APIs REST",
    "Bases de datos SQL y NoSQL",
    "Soporte TI",
    "Soporte técnico",
    "Infraestructura",
    "Redes",
    "Sistemas",
    "Cloud y DevOps",
    "Análisis de datos",
    "Automatización",
    "Ciberseguridad",
]


def build_default_match_criteria() -> JobMatchCriteria:
    """Construye los criterios de coincidencia iniciales basados en Ñuble e Informática."""
    return JobMatchCriteria(
        preferred_regions=["Ñuble"],
        priority_comunas=COMUNAS_PRIORITARIAS_DEFAULT,
        interest_areas=DEFAULT_AREAS,
        interest_keywords=[
            "python",
            "javascript",
            "typescript",
            "node",
            "sql",
            "backend",
            "full stack",
            "web",
            "soporte",
            "redes",
            "linux",
            "cloud",
            "devops",
            "informática",
            "desarrollador",
            "programador",
            "sistemas",
        ],
        exclude_internships=True,
        exclude_thesis=True,
        min_salary=None,
        weight_location=0.25,
        weight_skills=0.25,
        weight_experience=0.15,
        weight_education=0.10,
        weight_modality=0.10,
        weight_contract=0.05,
        weight_salary=0.10,
    )


def criteria_from_db_preferences(db_prefs: Any) -> JobMatchCriteria:
    """Convierte las preferencias almacenadas en BD a JobMatchCriteria."""

    def parse_json_list(val: str | None, default: list) -> list:
        if not val:
            return default
        try:
            return json.loads(val)
        except Exception:
            return default

    regions = parse_json_list(getattr(db_prefs, "preferred_regions", None), ["Ñuble"])
    comunas = parse_json_list(getattr(db_prefs, "preferred_comunas", None), [])
    priority_comunas = parse_json_list(
        getattr(db_prefs, "priority_comunas", None), COMUNAS_PRIORITARIAS_DEFAULT
    )
    areas = parse_json_list(getattr(db_prefs, "interest_areas", None), DEFAULT_AREAS)
    keywords = parse_json_list(getattr(db_prefs, "interest_keywords", None), [])

    return JobMatchCriteria(
        preferred_regions=regions,
        preferred_comunas=comunas,
        priority_comunas=priority_comunas,
        interest_areas=areas,
        interest_keywords=keywords or [a.lower() for a in areas],
        exclude_internships=getattr(db_prefs, "exclude_internships", True),
        exclude_thesis=getattr(db_prefs, "exclude_thesis", True),
        min_salary=getattr(db_prefs, "min_salary", None),
        preferred_modality=getattr(db_prefs, "preferred_modality", None),
        preferred_contract=getattr(db_prefs, "preferred_contract", None),
        weight_location=getattr(db_prefs, "weight_location", 0.25),
        weight_skills=getattr(db_prefs, "weight_skills", 0.25),
        weight_experience=getattr(db_prefs, "weight_experience", 0.15),
        weight_education=getattr(db_prefs, "weight_education", 0.10),
        weight_modality=getattr(db_prefs, "weight_modality", 0.10),
        weight_contract=getattr(db_prefs, "weight_contract", 0.05),
        weight_salary=getattr(db_prefs, "weight_salary", 0.10),
    )
