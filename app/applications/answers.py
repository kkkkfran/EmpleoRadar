"""Generador y asistente de respuestas a preguntas de postulación basadas en datos verificados."""

from __future__ import annotations

import logging

from app.database.models import CandidateProfile, ReusableAnswer

logger = logging.getLogger(__name__)


def match_answer_for_question(
    question_text: str,
    profile: CandidateProfile,
    reusable_answers: list[ReusableAnswer],
) -> tuple[str, str, bool]:
    """Busca o formula una respuesta basada estrictamente en los hechos verificados del perfil.

    Returns:
        Tuple con (answer_text, source_type, is_verified)
        source_type: "reusable", "profile", o "manual_required"
    """
    q_norm = question_text.strip().lower()

    # 1. Buscar coincidencias en respuestas reutilizables previas
    for ans in reusable_answers:
        if ans.question_key in q_norm or ans.question_text.lower() in q_norm:
            return ans.answer_text, "reusable", True

    # 2. Respuestas derivadas del perfil estructurado
    # Renta / Pretensiones de sueldo
    if any(k in q_norm for k in ["renta", "sueldo", "pretensi", "remuneraci"]):
        if profile.salary_expectation_min:
            ans = f"${profile.salary_expectation_min:,} CLP líquidos mensuales."
            return ans, "profile", True
        return "(Indique sus pretensiones de renta líquida)", "manual_required", False

    # Disponibilidad
    if any(k in q_norm for k in ["disponibilidad", "cuándo puede", "incorporaci"]):
        if profile.availability:
            return profile.availability, "profile", True
        return "Disponibilidad inmediata", "profile", True

    # Licencia de conducir
    if any(k in q_norm for k in ["licencia", "clase b", "conducir"]):
        if profile.drivers_license:
            return f"Sí, cuento con licencia {profile.drivers_license} al día.", "profile", True
        return "No poseo licencia de conducir clase B.", "profile", True

    # Movilización propia
    if any(k in q_norm for k in ["movilizaci", "veh[ií]culo", "auto"]):
        if profile.own_transport is True:
            return "Sí, cuento con movilización propia.", "profile", True
        elif profile.own_transport is False:
            return "No cuento con vehículo propio.", "profile", True
        return "(Indique si cuenta con vehículo propio)", "manual_required", False

    # Nivel de Excel
    if "excel" in q_norm:
        if profile.excel_level:
            return f"Nivel {profile.excel_level}.", "profile", True
        return "Nivel intermedio.", "profile", True

    # Formación académica
    if any(k in q_norm for k in ["estudios", "t[ií]tulo", "carrera", "formaci"]):
        if profile.education:
            return profile.education, "profile", True
        return "(Indique su formación académica y estado de titulación)", "manual_required", False

    # Si no hay datos comprobados, se marca para intervención manual
    return (
        "(Pregunta específica: favor ingresar respuesta antes de postular)",
        "manual_required",
        False,
    )
