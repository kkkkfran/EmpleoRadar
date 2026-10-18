"""Normalizador y analizador de ofertas laborales."""

from __future__ import annotations

import contextlib
import re
from typing import Any

from bs4 import BeautifulSoup

from app.database.models import ContractType, WorkModality, WorkSchedule
from app.jobs.models import JobPayload
from app.jobs.regions_data import find_comuna_and_region

# Patrones de exclusión de prácticas y memorias (evaluados sobre texto sin tildes)
_INTERNSHIP_PATTERNS = [
    re.compile(r"\bpractica\s+profesional\b", re.IGNORECASE),
    re.compile(r"\balumno\s+en\s+practica\b", re.IGNORECASE),
    re.compile(r"\bestudiante\s+en\s+practica\b", re.IGNORECASE),
    re.compile(r"\bpractica\s+laboral\b", re.IGNORECASE),
    re.compile(r"\bmemoria\s+de\s+titulo\b", re.IGNORECASE),
    re.compile(r"\bmemorista\b", re.IGNORECASE),
    re.compile(r"\binternado\b", re.IGNORECASE),
    re.compile(r"\bpasante\b|\bpasantia\b", re.IGNORECASE),
]

# Patrones de modalidad (evaluados sobre texto sin tildes)
_REMOTE_PATTERNS = [
    re.compile(
        r"\bremoto\b|\bteletrabajo\b|\bhome\s*office\b|\b100%\s*remoto\b|\btrabajo\s+a\s+distancia\b",
        re.IGNORECASE,
    ),
]
_HYBRID_PATTERNS = [
    re.compile(r"\bhibrid[oa]s?\b|\bmix\s+presencial\b|\bsemi[-\s]presencial\b", re.IGNORECASE),
]
_PRESENTIAL_PATTERNS = [
    re.compile(
        r"\bpresencial\b|\ben\s+terreno\b|\ben\s+oficina\b|\ben\s+sucursal\b", re.IGNORECASE
    ),
]

# Patrones de tipo de contrato
_CONTRACT_PATTERNS = [
    (
        re.compile(
            r"\bindefinido\b|\bplazo\s+indefinido\b|\bcontrato\s+indefinido\b", re.IGNORECASE
        ),
        ContractType.INDEFINIDO,
    ),
    (re.compile(r"\bplazo\s+fijo\b|\bpor\s+periodo\b", re.IGNORECASE), ContractType.PLAZO_FIJO),
    (
        re.compile(
            r"\bhonorarios\b|\bboleta\s+de\s+honorarios\b|\bprestacion\s+de\s+servicios\b",
            re.IGNORECASE,
        ),
        ContractType.HONORARIOS,
    ),
    (
        re.compile(r"\bpor\s+proyecto\b|\bobra\s+o\s+faena\b|\bpor\s+obra\b", re.IGNORECASE),
        ContractType.OBRA_O_PROYECTO,
    ),
    (re.compile(r"\bpart[-\s]?time\b|\bmedia\s+jornada\b", re.IGNORECASE), ContractType.PART_TIME),
]

# Patrones de jornada
_SCHEDULE_PATTERNS = [
    (
        re.compile(r"\bcompleta\b|\b44\s*horas\b|\b45\s*horas\b|\bfull[-\s]?time\b", re.IGNORECASE),
        WorkSchedule.COMPLETA,
    ),
    (
        re.compile(r"\bparcial\b|\bpart[-\s]?time\b|\b20\s*horas\b|\b30\s*horas\b", re.IGNORECASE),
        WorkSchedule.PARCIAL,
    ),
    (re.compile(r"\bturnos\b|\brottativo\b|\b4x3\b|\b7x7\b", re.IGNORECASE), WorkSchedule.TURNOS),
]


def clean_html(text: str | None) -> str:
    """Limpia etiquetas HTML y normaliza espacios en blanco."""
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    cleaned = soup.get_text(separator=" ")
    # Normalizar espacios
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned)
    return cleaned.strip()


def is_internship_offer(title: str, description: str | None = None) -> bool:
    """Detecta si una oferta corresponde a práctica profesional, memoria o pasantía."""
    from app.jobs.regions_data import normalize_text_match

    combined = normalize_text_match(f"{title} {description or ''}")
    return any(pattern.search(combined) for pattern in _INTERNSHIP_PATTERNS)


def detect_modality(
    title: str, text: str | None = None, explicit: str | None = None
) -> WorkModality:
    """Identifica la modalidad de trabajo."""
    from app.jobs.regions_data import normalize_text_match

    if explicit:
        norm_exp = normalize_text_match(explicit)
        if "hibrid" in norm_exp:
            return WorkModality.HIBRIDO
        if "remot" in norm_exp or "tele" in norm_exp or "home" in norm_exp:
            return WorkModality.REMOTO
        if "presenc" in norm_exp or "terren" in norm_exp:
            return WorkModality.PRESENCIAL

    combined = normalize_text_match(f"{title} {text or ''}")
    if any(p.search(combined) for p in _HYBRID_PATTERNS):
        return WorkModality.HIBRIDO
    if any(p.search(combined) for p in _REMOTE_PATTERNS):
        return WorkModality.REMOTO
    if any(p.search(combined) for p in _PRESENTIAL_PATTERNS):
        return WorkModality.PRESENCIAL

    return WorkModality.DESCONOCIDO


def detect_contract_type(text: str | None, explicit: str | None = None) -> ContractType:
    """Identifica el tipo de contrato legal en Chile."""
    if explicit:
        norm_exp = explicit.strip().lower()
        for pattern, c_type in _CONTRACT_PATTERNS:
            if pattern.search(norm_exp):
                return c_type

    if not text:
        return ContractType.DESCONOCIDO

    for pattern, c_type in _CONTRACT_PATTERNS:
        if pattern.search(text):
            return c_type
    return ContractType.DESCONOCIDO


def detect_schedule(text: str | None, explicit: str | None = None) -> WorkSchedule:
    """Identifica el tipo de jornada laboral."""
    if explicit:
        norm_exp = explicit.strip().lower()
        for pattern, sched in _SCHEDULE_PATTERNS:
            if pattern.search(norm_exp):
                return sched

    if not text:
        return WorkSchedule.DESCONOCIDO

    for pattern, sched in _SCHEDULE_PATTERNS:
        if pattern.search(text):
            return sched
    return WorkSchedule.DESCONOCIDO


def parse_salary_clp(text: str | None) -> tuple[int | None, int | None, str | None]:
    """Extrae rango salarial en pesos chilenos (CLP) y tipo (bruto/líquido)."""
    if not text:
        return None, None, None

    cleaned = text.lower()
    salary_type: str | None = None
    if "liquido" in cleaned or "líquido" in cleaned:
        salary_type = "liquido"
    elif "bruto" in cleaned:
        salary_type = "bruto"

    # Buscar valores expresados con signo peso o números grandes
    # Ejemplos: $1.200.000, 800000 - 1200000, 1.500.000 a 2.000.000
    amounts = []
    # Buscar patrones con puntos como separadores de miles
    matches_dots = re.findall(r"\$?\s*([1-9]\d{0,2}(?:\.\d{3}){1,2})", text)
    if matches_dots:
        for m in matches_dots:
            val = int(m.replace(".", "").strip())
            if 100_000 <= val <= 20_000_000:
                amounts.append(val)

    if not amounts:
        # Buscar números enteros simples de 6 o 7 dígitos
        matches_digits = re.findall(r"\$?\s*([1-9]\d{5,7})\b", text)
        for m in matches_digits:
            val = int(m)
            if 100_000 <= val <= 20_000_000:
                amounts.append(val)

    if not amounts:
        return None, None, salary_type

    amounts = sorted(set(amounts))
    if len(amounts) == 1:
        return amounts[0], amounts[0], salary_type
    return amounts[0], amounts[-1], salary_type


def detect_experience_requirements(text: str | None) -> tuple[str | None, bool]:
    """Detecta requisitos de experiencia y si es explícitamente junior o sin experiencia."""
    if not text:
        return None, False

    cleaned = text.lower()
    is_junior_or_no_exp = False

    if any(
        k in cleaned
        for k in [
            "sin experiencia",
            "no requiere experiencia",
            "primer empleo",
            "recién egresado",
            "junior",
            "jr.",
        ]
    ):
        is_junior_or_no_exp = True

    # Buscar cantidad de años requeridos
    match = re.search(r"(\d+)\s*(?:a\s*\d+)?\s*(?:año|años|ano|anos)\s+de\s+experiencia", cleaned)
    if match:
        years_str = match.group(0)
        return years_str, is_junior_or_no_exp

    if is_junior_or_no_exp:
        return "Sin experiencia o Junior", True

    return None, False


def normalize_job_payload(
    raw: dict[str, Any],
    source_name: str,
) -> JobPayload:
    """Normaliza completamente los datos crudos extraídos de una fuente."""
    raw_title = clean_html(str(raw.get("title", "")))
    raw_desc = clean_html(str(raw.get("description", "")))
    raw_company = clean_html(str(raw.get("company", ""))) or "Empresa Confidencial"
    raw_location = clean_html(str(raw.get("location", "") or raw.get("location_raw", "")))
    url = str(raw.get("url", "")).strip()

    # Detección de prácticas y memorias
    is_internship = is_internship_offer(raw_title, raw_desc)
    if raw.get("is_internship") is True:
        is_internship = True

    # Detección de ubicación
    comuna, region = find_comuna_and_region(f"{raw_location} {raw_title} {raw_desc[:200]}")
    if not region and raw.get("region"):
        region = str(raw.get("region"))
    if not comuna and raw.get("comuna"):
        comuna = str(raw.get("comuna"))

    # Modalidad
    modality = detect_modality(raw_title, raw_desc, raw.get("modality"))

    # Contrato y Jornada
    contract = detect_contract_type(f"{raw_title} {raw_desc}", raw.get("contract_type"))
    if is_internship:
        contract = ContractType.PRACTICA

    schedule = detect_schedule(f"{raw_title} {raw_desc}", raw.get("schedule"))

    # Sueldo
    salary_min, salary_max, salary_type = parse_salary_clp(f"{raw.get('salary', '')} {raw_desc}")
    if raw.get("salary_min"):
        with contextlib.suppress(ValueError, TypeError):
            salary_min = int(raw["salary_min"])
    if raw.get("salary_max"):
        with contextlib.suppress(ValueError, TypeError):
            salary_max = int(raw["salary_max"])

    # Experiencia
    exp_req, _ = detect_experience_requirements(f"{raw_title} {raw_desc}")

    return JobPayload(
        source_name=source_name,
        external_id=str(raw.get("external_id") or raw.get("id") or ""),
        title=raw_title,
        company=raw_company,
        description=raw_desc,
        location_raw=raw_location,
        region=region,
        comuna=comuna,
        modality=modality,
        contract_type=contract,
        schedule=schedule,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_type=salary_type,
        requirements=raw.get("requirements"),
        experience_required=exp_req,
        education_required=raw.get("education_required"),
        url=url,
        published_at=raw.get("published_at"),
        is_internship=is_internship,
        raw_data=raw,
    )
