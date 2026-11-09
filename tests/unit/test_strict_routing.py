"""Reglas estrictas solicitadas para los dos canales de Discord."""

import pytest

from app.database.models import WorkModality
from app.jobs.models import JobPayload
from app.jobs.routing import route_job

IT = 1
GENERAL = 2


def job(title: str, location: str, **kwargs) -> JobPayload:
    return JobPayload(
        source_name="test",
        title=title,
        location_raw=location,
        url="https://example.com/job",
        **kwargs,
    )


def test_it_only_in_allowed_zones_or_remote():
    assert route_job(job("Desarrollador Python", "Chillán"), IT, GENERAL) == IT
    assert route_job(job("Soporte TI", "Chillán Viejo"), IT, GENERAL) == IT
    assert route_job(job("Backend Developer", "Antofagasta"), IT, GENERAL) is None
    remote = job("Backend Developer", "Chile", modality=WorkModality.REMOTO)
    assert route_job(remote, IT, GENERAL) == IT


def test_administrative_role_is_not_mistaken_for_it():
    role = job(
        "Asistente Administrativa de RRHH",
        "Concepción",
        description="Uso de plataforma y gestión de información.",
    )
    assert route_job(role, IT, GENERAL) is None


def test_general_jobs_are_chillan_accessible_roles_without_degree():
    assert route_job(job("Cajero de supermercado", "Chillán"), IT, GENERAL) == GENERAL
    assert route_job(job("Cajero de supermercado", "Concepción"), IT, GENERAL) is None
    professional = job(
        "Cajero administrativo",
        "Chillán",
        description="Requiere título profesional en Administración de Empresas.",
    )
    assert route_job(professional, IT, GENERAL) is None


def test_internships_never_route():
    internship = job("Práctica profesional informática", "Santiago", is_internship=True)
    assert route_job(internship, IT, GENERAL) is None


@pytest.mark.parametrize("location", ["Ñuble", "Ninhue", "San Carlos, Ñuble", "Concepción", "Santiago"])
@pytest.mark.parametrize("modality", [WorkModality.PRESENCIAL, WorkModality.HIBRIDO])
def test_local_alerts_do_not_cover_rest_of_nuble_or_other_regions(location, modality):
    assert route_job(job("Analista TI", location, modality=modality), IT, GENERAL) is None
    assert route_job(job("Bodeguero", location, modality=modality), IT, GENERAL) is None


@pytest.mark.parametrize("title", ["Ingeniera informática", "Técnico informático", "Analista TI", "Soporte TI", "QA Engineer"])
def test_it_professions_are_supported(title):
    role = job(title, "Chillán Viejo", description="Desarrollo de software y pruebas de sistemas")
    assert route_job(role, IT, GENERAL) == IT


@pytest.mark.parametrize("title", ["Técnico refrigeración", "Analista calidad alimentaria", "Analista contable", "Soporte técnico de refrigeración"])
def test_non_it_technical_roles_are_not_it(title):
    role = job(title, "Chillán", description="Uso de sistemas informáticos, SQL y software de gestión")
    assert route_job(role, IT, GENERAL) is None


@pytest.mark.parametrize("title", ["Bodeguera", "Cajeras de supermercado", "Ayudante de cocina", "Asistente de restaurante", "Reponedores", "Garzona"])
def test_accessible_roles_and_gender_variants(title):
    role = job(title, "Chillán Viejo", description="Enseñanza media completa. Sin experiencia. Seguro médico complementario.")
    assert route_job(role, IT, GENERAL) == GENERAL


@pytest.mark.parametrize("education", ["Título profesional", "Técnico de nivel superior", "Técnico nivel superior", "Formación técnica", "Estudios universitarios completos", "Técnico en administración"])
def test_general_channel_rejects_required_professions(education):
    role = job("Asistente administrativo", "Chillán", education_required=education)
    assert route_job(role, IT, GENERAL) is None


def test_optional_degree_is_not_mandatory():
    role = job("Asistente de ventas", "Chillán", description="Enseñanza media completa. Título técnico deseable, no excluyente.")
    assert route_job(role, IT, GENERAL) == GENERAL
    role.description = "No requiere título universitario ni experiencia."
    assert route_job(role, IT, GENERAL) == GENERAL
    role.description = "No requiere experiencia, título universitario obligatorio."
    assert route_job(role, IT, GENERAL) is None


@pytest.mark.parametrize("location", ["Chile", "LATAM", "Worldwide", "Santiago, Chile"])
def test_remote_jobs_in_both_categories_can_be_done_from_chile(location):
    assert route_job(job("Backend Developer", location, modality=WorkModality.REMOTO), IT, GENERAL) == IT
    assert route_job(job("Atención al cliente", location, modality=WorkModality.REMOTO), IT, GENERAL) == GENERAL


def test_foreign_country_remote_restriction_is_respected():
    role = job("Backend Developer", "USA only", modality=WorkModality.REMOTO)
    assert route_job(role, IT, GENERAL) is None


def test_remote_without_published_country_restriction_is_included():
    role = job("Backend Developer", "Remoto", modality=WorkModality.REMOTO,
               raw_data={"countries": ["Remoto"], "remote_zone": None})
    assert route_job(role, IT, GENERAL) == IT
    role.raw_data = {"countries": ["Remoto"], "remote_zone": "USA only"}
    assert route_job(role, IT, GENERAL) is None
    role.location_raw = "Santiago, Chile"
    role.raw_data = {"allowed_countries": ["Mexico", "Colombia"]}
    assert route_job(role, IT, GENERAL) is None


def test_explicit_comuna_wins_over_other_location_mentions():
    role = job("Bodeguero", "Ninhue, cerca de Chillán", comuna="Ninhue")
    assert route_job(role, IT, GENERAL) is None
