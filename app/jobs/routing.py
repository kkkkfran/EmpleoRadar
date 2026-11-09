"""Reglas de los canales: Chillán/Chillán Viejo y remoto disponible desde Chile."""

from __future__ import annotations

import json
import re

from app.database.models import WorkModality
from app.jobs.models import JobPayload
from app.jobs.normalizer import is_internship_offer
from app.jobs.regions_data import REGIONES_CHILE, find_comuna_and_region, normalize_text_match

LOCAL_COMUNAS = {"chillan", "chillan viejo"}
IT_TITLE_TERMS = (
    "informatica", "informatico", "software", "desarrollador", "desarrolladora",
    "developer", "programador", "programadora", "programming", "backend", "frontend",
    "full stack", "fullstack", "devops", "cloud", "ciberseguridad", "cybersecurity",
    "data engineer", "data scientist", "analista de datos", "data analyst", "tester",
    "soporte ti", "soporte computacional", "administrador de sistemas", "ingeniero de sistemas",
    "analista de sistemas", "dba", "base de datos", "redes y telecomunicaciones",
    "web developer", "scrum master", "help desk", "helpdesk", "service desk", "mesa de ayuda",
)
TECH_TERMS = (
    "python", "javascript", "typescript", "react", "angular", "vue", "node.js", "java",
    "spring", ".net", "c#", "php", "laravel", "django", "fastapi", "docker", "kubernetes",
    "aws", "azure", "gcp", "linux", "sql", "postgresql", "mongodb", "api rest",
    "informatica", "computacion", "computadores", "computacionales", "hardware", "software",
    "servidores", "redes informaticas", "tecnologias de informacion",
)
IT_ROLE_HINTS = (
    "ingeniero", "ingeniera", "analista", "consultor", "consultora", "especialista",
    "tecnico", "tecnica", "lead", "architect", "soporte", "qa", "testing",
)
NON_IT_SPECIALTIES = (
    "refrigeracion", "electrico", "electrica", "electromecanico", "alimentos", "alimentaria",
    "laboratorio", "contable", "contabilidad", "financiero", "financiera", "recursos humanos",
)
GENERAL_ROLE_PATTERN = re.compile(
    r"\b(?:cajer[oa]s?|vendedor(?:a|es|as)?|asistentes? de (?:ventas|restaurante|bodega|cocina)"
    r"|asistentes? administrativ[oa]s?|organizadores?|reponedor(?:a|es|as)?|bodeguer[oa]s?"
    r"|operari[oa]s?|ayudantes?|auxiliares?|auxiliar|garzon(?:a|es|as)?|meser[oa]s?|coper[oa]s?"
    r"|cociner[oa]s?|baristas?|panader[oa]s?|guardias?|conserjes?|aseo|limpieza|pickers?"
    r"|embalador(?:a|es|as)?|despachador(?:a|es|as)?|atencion (?:al|a) cliente[s]?|call center"
    r"|promotor(?:a|es|as)?|mercaderistas?|multifuncional(?:es)?|chofer(?:es)?"
    r"|conductor(?:a|es|as)?|peonetas?|recepcionistas?|anfitrion(?:a|es|as)?|lavador(?:a|es|as)?"
    r"|jornales?|digitador(?:a|es|as)?|repartidor(?:a|es|as)?)\b"
)
PROFESSIONAL_ROLE_PATTERN = re.compile(
    r"\b(?:ingenier[oa]|abogad[oa]|psicolog[oa]|enfermer[oa]|medic[oa]|odontolog[oa]"
    r"|kinesiolog[oa]|contador|contadora|trabajador(?:a)? social|tecnic[oa]"
    r"|enfermeria|farmacia|paramedico)\b"
)
DEGREE_PATTERN = re.compile(
    r"\b(?:titulo (?:profesional|universitario|tecnico)|carrera universitaria|licenciatura"
    r"|ingenieria|administracion de empresas|contador auditor|profesional titulad[oa]"
    r"|tecnic[oa] (?:de )?nivel superior|estudios (?:superiores|universitarios)"
    r"|educacion superior|formacion (?:tecnica|universitaria|profesional)"
    r"|tecnic[oa] (?:en|titulado)|titulad[oa] (?:en|de))\b"
)
OPTIONAL_DEGREE_PATTERN = re.compile(
    r"\b(?:no (?:se )?(?:requiere|exige|necesita|es necesario)|sin (?:necesidad de )?"
    r"(?:titulo|estudios)|no excluyente|deseable|opcional|no obligatorio)\b"
)


def _contains(text: str, terms: tuple[str, ...]) -> bool:
    return any(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text) for term in terms)


def is_it_job(job: JobPayload) -> bool:
    title = normalize_text_match(job.title)
    body = normalize_text_match(f"{job.description or ''} {job.requirements or ''}")
    if _contains(title, IT_TITLE_TERMS):
        return True
    return (
        not _contains(title, NON_IT_SPECIALTIES)
        and _contains(title, IT_ROLE_HINTS)
        and (_contains(f"{title} {body}", TECH_TERMS) or _contains(title, ("ti", "tic", "it")))
    )


def is_remote_available_from_chile(job: JobPayload) -> bool:
    """Acepta remoto sin restricción publicada o compatible con residencia en Chile."""
    if job.modality != WorkModality.REMOTO:
        return False
    compatible = ("chile", "cl", "latam", "latinoamerica", "latin america", "south america",
                  "sudamerica", "worldwide", "global", "anywhere", "todo el mundo")
    raw = job.raw_data or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            raw = {}
    if not isinstance(raw, dict):
        raw = {}
    neutral = {"", "remoto", "remote", "teletrabajo", "home office", "100% remoto"}
    countries = raw.get("allowed_countries") or raw.get("countries") or []
    if isinstance(countries, str):
        countries = [countries]
    if isinstance(countries, (list, tuple)):
        countries = [normalize_text_match(str(country)) for country in countries]
        countries = [country for country in countries if country not in neutral]
    # El dato estructurado tiene precedencia sobre la sede de la empresa.
    if countries and not any(_contains(str(country), compatible) for country in countries):
        return False
    remote_zone = normalize_text_match(str(raw.get("remote_zone") or ""))
    if remote_zone and remote_zone not in neutral and not _contains(remote_zone, compatible):
        return False
    if countries or (remote_zone and _contains(remote_zone, compatible)):
        return True
    location = normalize_text_match(
        f"{getattr(job, 'location_raw', None) or getattr(job, 'location', None) or ''}"
    )
    if _contains(location, compatible):
        return True
    comuna, region = find_comuna_and_region(location)
    if comuna or region:
        return True
    if location.strip() in neutral:
        return not job.region or job.region in REGIONES_CHILE
    return False


def is_allowed_it_location(job: JobPayload) -> bool:
    if job.modality == WorkModality.REMOTO:
        return is_remote_available_from_chile(job)
    if job.comuna:
        return normalize_text_match(job.comuna) in LOCAL_COMUNAS
    location = normalize_text_match(
        f"{getattr(job, 'location_raw', None) or getattr(job, 'location', None) or ''}"
    )
    comuna, _ = find_comuna_and_region(location)
    return normalize_text_match(comuna or "") in LOCAL_COMUNAS


def requires_professional_qualification(job: JobPayload) -> bool:
    """Descarta carreras obligatorias, sin confundir beneficios médicos con formación."""
    if PROFESSIONAL_ROLE_PATTERN.search(normalize_text_match(job.title)):
        return True
    for text in (job.education_required, job.requirements, job.description):
        if not text:
            continue
        # 'No requiere experiencia' no debe ocultar un título obligatorio posterior.
        for clause in re.split(r"[.;\n]|,|\b(?:pero|y)\b", normalize_text_match(text)):
            if DEGREE_PATTERN.search(clause) and not OPTIONAL_DEGREE_PATTERN.search(clause):
                return True
    return False


def is_accessible_chillan_job(job: JobPayload) -> bool:
    return (
        is_allowed_it_location(job)
        and bool(GENERAL_ROLE_PATTERN.search(normalize_text_match(job.title)))
        and not requires_professional_qualification(job)
        and not is_it_job(job)
    )


def route_job(job: JobPayload, it_channel_id: int, chillan_channel_id: int) -> int | None:
    """Devuelve un canal solo cuando la oferta cumple categoría y ubicación."""
    if job.is_internship or is_internship_offer(job.title, job.description):
        return None
    if is_it_job(job) and is_allowed_it_location(job):
        return it_channel_id
    if is_accessible_chillan_job(job):
        return chillan_channel_id
    return None
