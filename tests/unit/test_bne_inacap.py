"""Pruebas unitarias para los conectores de BNE y Emplea INACAP."""

from datetime import datetime

from app.sources.bne import BNESource
from app.sources.inacap import InacapSource


def test_parse_bne_item() -> None:
    source = BNESource()
    raw_item = {
        "codigo": "BNE-9988",
        "titulo": "Desarrollador Full Stack Python",
        "empresa": "Tech Chile SpA",
        "descripcion": "Desarrollo de APIs REST y frontend con React.",
        "comuna": "Chillán",
        "region": "Región de Ñuble",
        "fecha": "17/10/26",
    }
    payload = source._parse_bne_item(raw_item)
    assert payload is not None
    assert payload.title == "Desarrollador Full Stack Python"
    assert payload.company == "Tech Chile SpA"
    assert payload.comuna == "Chillán"
    assert payload.region == "Ñuble"
    assert payload.url == "https://www.bne.cl/oferta/BNE-9988"
    assert payload.external_id == "BNE-9988"
    assert payload.published_at == datetime(2026, 10, 17, 0, 0)
    assert payload.dedup_hash is not None


def test_parse_inacap_jsonld_item() -> None:
    source = InacapSource()
    raw_jsonld = {
        "title": "Ingeniero de Software DevOps",
        "url": "https://emplea.inacap.cl/trabajo/ingeniero-devops-12345",
        "hiringOrganization": {"name": "Consultora TI Cloud"},
        "jobLocation": {"address": "Concepción, Biobío"},
        "description": "Automatización CI/CD, Kubernetes y Docker.",
        "datePosted": "2026-10-16",
    }
    payload = source._parse_jsonld_job(raw_jsonld)
    assert payload is not None
    assert payload.title == "Ingeniero de Software DevOps"
    assert payload.company == "Consultora TI Cloud"
    assert payload.comuna == "Concepción"
    assert payload.region == "Biobío"
    assert payload.external_id == "12345"
    assert payload.published_at == datetime(2026, 10, 16, 0, 0)
    assert payload.dedup_hash is not None

