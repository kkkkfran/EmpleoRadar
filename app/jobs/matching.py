"""Motor de coincidencia, filtrado y cálculo de puntuación (0 a 100) para ofertas laborales."""

from __future__ import annotations

import re

from app.database.models import ContractType, WorkModality
from app.jobs.models import JobMatchCriteria, JobMatchResult, JobPayload
from app.jobs.regions_data import COMUNAS_NUBLE, normalize_text_match

# Palabras clave por defecto si no están configuradas
DEFAULT_INTEREST_KEYWORDS: list[str] = [
    # Informática y Desarrollo
    "ingeniería en informática",
    "ingeniero informático",
    "ingeniero en informática",
    "desarrollo backend",
    "backend",
    "full stack",
    "fullstack",
    "desarrollo web",
    "python",
    "javascript",
    "typescript",
    "node.js",
    "nodejs",
    "api rest",
    "apis rest",
    # Bases de datos
    "sql",
    "postgresql",
    "sqlite",
    "mysql",
    "nosql",
    "mongodb",
    # Soporte y Redes
    "soporte ti",
    "soporte técnico",
    "soporte computacional",
    "técnico en informática",
    "infraestructura",
    "redes",
    "networking",
    "sistemas",
    "administrador de sistemas",
    # Cloud y Datos
    "cloud",
    "devops",
    "docker",
    "análisis de datos",
    "analista de datos",
    "automatización",
    "ciberseguridad",
    "seguridad informática",
    "qa",
    "testing",
]


def evaluate_job_match(
    job: JobPayload,
    criteria: JobMatchCriteria,
) -> JobMatchResult:
    """Evalúa la compatibilidad de una vacante frente a las preferencias del usuario.

    Calcula una puntuación transparente de 0 a 100 con desglose y explicaciones claras.
    """
    # 1. Reglas excluyentes obligatorias
    if criteria.exclude_internships and job.is_internship:
        return JobMatchResult(
            score=0,
            is_excluded=True,
            exclusion_reason="Oferta descartada automáticamente por ser práctica profesional o memoria.",
            summary="Práctica profesional / Memoria excluida según configuración.",
        )

    title_desc = f"{job.title} {job.description or ''}"
    norm_content = normalize_text_match(title_desc)

    reasons: list[str] = []
    missing: list[str] = []
    breakdown: dict[str, float] = {}

    # --- Puntuación de Ubicación (weight_location) ---
    loc_score = 0.0
    is_remote = job.modality == WorkModality.REMOTO
    comuna_norm = normalize_text_match(job.comuna or "")
    region_norm = normalize_text_match(job.region or "")

    if is_remote:
        loc_score = 1.0
        reasons.append("Modalidad 100% Remota: compatible desde cualquier ubicación.")
    elif job.comuna and any(
        normalize_text_match(p) == comuna_norm for p in criteria.priority_comunas
    ):
        loc_score = 1.0
        reasons.append(f"Ubicación prioritaria directa: {job.comuna}.")
    elif job.comuna and any(normalize_text_match(c) == comuna_norm for c in COMUNAS_NUBLE):
        loc_score = 0.85
        reasons.append(f"Ubicación en Región de Ñuble: {job.comuna}.")
    elif job.region and any(
        normalize_text_match(r) == region_norm for r in criteria.preferred_regions
    ):
        loc_score = 0.70
        reasons.append(f"Ubicación en región preferida: {job.region}.")
    elif not job.comuna and not job.region:
        loc_score = 0.40
        missing.append("Ubicación específica no indicada en la oferta.")
    else:
        loc_score = 0.10
        missing.append(f"Ubicación fuera de zona preferida ({job.comuna or job.region}).")

    breakdown["location"] = loc_score * criteria.weight_location

    # --- Puntuación de Habilidades y Áreas Tecnológicas (weight_skills) ---
    keywords = criteria.interest_keywords or DEFAULT_INTEREST_KEYWORDS
    matched_skills = []
    for kw in keywords:
        norm_kw = normalize_text_match(kw)
        if re.search(r"\b" + re.escape(norm_kw) + r"\b", norm_content):
            matched_skills.append(kw)

    if matched_skills:
        # Entre 1 y 4 o más coincidencias
        skill_ratio = min(1.0, len(matched_skills) / 3.0)
        skills_score = 0.4 + (0.6 * skill_ratio)
        sample = ", ".join(matched_skills[:4])
        reasons.append(f"Coincide con tecnologías/áreas clave: {sample}.")
    else:
        skills_score = 0.10
        missing.append("No se detectaron coincidencias explícitas con las tecnologías de interés.")

    breakdown["skills"] = skills_score * criteria.weight_skills

    # --- Puntuación de Experiencia (weight_experience) ---
    exp_score = 0.5  # Neutral por defecto
    if job.experience_required:
        if (
            "sin experiencia" in job.experience_required.lower()
            or "junior" in job.experience_required.lower()
        ):
            exp_score = 1.0
            reasons.append(f"Requisito de experiencia amigable: {job.experience_required}.")
        else:
            exp_score = 0.7
            reasons.append(f"Requisito de experiencia: {job.experience_required}.")
    else:
        exp_score = 0.6
        missing.append("Años de experiencia requeridos no especificados.")

    breakdown["experience"] = exp_score * criteria.weight_experience

    # --- Puntuación de Formación (weight_education) ---
    edu_score = 0.5
    if any(
        k in norm_content
        for k in [
            "informatico",
            "informatica",
            "computacion",
            "analista programador",
            "desarrollador",
        ]
    ):
        edu_score = 1.0
        reasons.append("Formación afín al área de informática / tecnologías de información.")
    else:
        edu_score = 0.4

    breakdown["education"] = edu_score * criteria.weight_education

    # --- Puntuación de Modalidad (weight_modality) ---
    mod_score = 0.5
    if criteria.preferred_modality:
        if job.modality.value == criteria.preferred_modality.lower():
            mod_score = 1.0
            reasons.append(f"Modalidad coincide exactamente con preferencia: {job.modality.value}.")
        elif is_remote:
            mod_score = 0.9
            reasons.append("Modalidad remota altamente valorada.")
        elif job.modality == WorkModality.DESCONOCIDO:
            mod_score = 0.5
            missing.append("Modalidad de trabajo no especificada.")
        else:
            mod_score = 0.3
    else:
        # Sin preferencia estricta: remoto e híbrido preferidos
        if is_remote:
            mod_score = 1.0
        elif job.modality == WorkModality.HIBRIDO:
            mod_score = 0.8
        elif job.modality == WorkModality.PRESENCIAL:
            mod_score = 0.6
        else:
            mod_score = 0.5

    breakdown["modality"] = mod_score * criteria.weight_modality

    # --- Puntuación de Tipo de Contrato (weight_contract) ---
    cont_score = 0.5
    if job.contract_type == ContractType.INDEFINIDO:
        cont_score = 1.0
        reasons.append("Contrato de tipo Indefinido.")
    elif job.contract_type in (ContractType.PLAZO_FIJO, ContractType.OBRA_O_PROYECTO):
        cont_score = 0.7
        reasons.append(f"Tipo de contrato: {job.contract_type.value}.")
    elif job.contract_type == ContractType.HONORARIOS:
        cont_score = 0.5
    else:
        cont_score = 0.4
        missing.append("Tipo de contrato no especificado.")

    breakdown["contract"] = cont_score * criteria.weight_contract

    # --- Puntuación de Salario (weight_salary) ---
    sal_score = 0.5
    if job.salary_min or job.salary_max:
        sal_val = job.salary_max or job.salary_min or 0
        if criteria.min_salary and sal_val < criteria.min_salary:
            sal_score = 0.2
            missing.append(f"Sueldo indicado (${sal_val:,}) inferior a pretensión mínima.")
        else:
            sal_score = 1.0
            reasons.append(
                f"Remuneración informada: ${sal_val:,} CLP ({job.salary_type or 'no especificado'})."
            )
    else:
        # No se descarta por no indicar sueldo
        sal_score = 0.6
        missing.append("Remuneración no publicada (a convenir).")

    breakdown["salary"] = sal_score * criteria.weight_salary

    # Total normalizado sobre la suma de pesos
    total_weight = sum(
        [
            criteria.weight_location,
            criteria.weight_skills,
            criteria.weight_experience,
            criteria.weight_education,
            criteria.weight_modality,
            criteria.weight_contract,
            criteria.weight_salary,
        ]
    )
    raw_total = sum(breakdown.values())
    final_score = int(round((raw_total / (total_weight or 1.0)) * 100))
    final_score = max(0, min(100, final_score))

    summary = f"Compatibilidad estimada: {final_score}/100. "
    if matched_skills:
        summary += f"Coincidencias en: {', '.join(matched_skills[:3])}. "
    if job.comuna:
        summary += f"Zona: {job.comuna}."

    return JobMatchResult(
        score=final_score,
        is_excluded=False,
        match_reasons=reasons,
        missing_criteria=missing,
        breakdown=breakdown,
        summary=summary,
    )
