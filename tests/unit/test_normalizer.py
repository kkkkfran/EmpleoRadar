"""Pruebas unitarias para el normalizador de ofertas laborales."""

from app.database.models import ContractType, WorkModality
from app.jobs.normalizer import (
    clean_html,
    detect_contract_type,
    detect_experience_requirements,
    detect_modality,
    is_internship_offer,
    normalize_job_payload,
    parse_salary_clp,
)


def test_clean_html():
    raw = "<p>Buscamos <b>Desarrollador Python</b> en Chillán.<br>Enviar CV.</p>"
    cleaned = clean_html(raw)
    assert "<p>" not in cleaned
    assert "<b>" not in cleaned
    assert "Desarrollador Python" in cleaned


def test_is_internship_detection():
    assert is_internship_offer("Alumno en práctica para soporte TI") is True
    assert is_internship_offer("Práctica profesional Ingeniería en Informática") is True
    assert is_internship_offer("Estudiante para memoria de título") is True
    assert is_internship_offer("Pasantía en desarrollo web") is True
    assert is_internship_offer("Ingeniero de Software Senior") is False
    assert is_internship_offer("Desarrollador Backend Junior") is False


def test_detect_modality():
    assert detect_modality("Desarrollador Python 100% Remoto") == WorkModality.REMOTO
    assert (
        detect_modality("Soporte Técnico Terreno", "Trabajo presencial en Chillán")
        == WorkModality.PRESENCIAL
    )
    assert (
        detect_modality("Analista TI", "Modalidad híbrida 2 días oficina") == WorkModality.HIBRIDO
    )
    assert detect_modality("Programador Java") == WorkModality.DESCONOCIDO


def test_detect_contract():
    assert (
        detect_contract_type("Contrato a plazo indefinido con beneficios")
        == ContractType.INDEFINIDO
    )
    assert detect_contract_type("Honorarios para proyecto específico") == ContractType.HONORARIOS
    assert detect_contract_type("Plazo fijo por 3 meses renovable") == ContractType.PLAZO_FIJO


def test_parse_salary_clp():
    # Con puntos
    s_min, s_max, s_type = parse_salary_clp("Sueldo: $1.200.000 líquidos")
    assert s_min == 1_200_000
    assert s_max == 1_200_000
    assert s_type == "liquido"

    # Rango
    s_min, s_max, s_type = parse_salary_clp("Renta entre $800.000 y $1.100.000 bruto")
    assert s_min == 800_000
    assert s_max == 1_100_000
    assert s_type == "bruto"

    # Sin sueldo
    s_min, s_max, s_type = parse_salary_clp("Renta a convenir según experiencia")
    assert s_min is None
    assert s_max is None


def test_detect_experience():
    exp, is_jr = detect_experience_requirements("Se requiere mínimo 2 años de experiencia en SQL")
    assert "2 años de experiencia" in exp
    assert is_jr is False

    exp, is_jr = detect_experience_requirements(
        "Cargo ideal para recién egresado o junior sin experiencia"
    )
    assert is_jr is True


def test_normalize_job_payload_full():
    raw = {
        "title": "Desarrollador Web Python / Django",
        "company": "Empresa Tecnológica Ñuble",
        "description": "<p>Buscamos programador para Chillán. Modalidad híbrida. Sueldo $1.200.000 líquidos.</p>",
        "location": "Chillán",
        "url": "https://ejemplo.cl/oferta/123",
    }
    payload = normalize_job_payload(raw, source_name="TestPortal")
    assert payload.title == "Desarrollador Web Python / Django"
    assert payload.company == "Empresa Tecnológica Ñuble"
    assert payload.comuna == "Chillán"
    assert payload.region == "Ñuble"
    assert payload.modality == WorkModality.HIBRIDO
    assert payload.salary_min == 1_200_000
    assert payload.salary_type == "liquido"
    assert payload.is_internship is False
