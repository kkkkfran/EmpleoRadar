"""Pruebas unitarias para datos geográficos y detección de comunas de Ñuble."""

from app.jobs.regions_data import (
    COMUNAS_NUBLE,
    COMUNAS_PRIORITARIAS_DEFAULT,
    find_comuna_and_region,
)


def test_nuble_comunas_count_and_no_duplicates():
    """Verifica que la Región de Ñuble tenga exactamente sus 21 comunas sin duplicados."""
    assert len(COMUNAS_NUBLE) == 21
    assert len(set(COMUNAS_NUBLE)) == 21
    # Verificar comunas clave
    assert "Chillán" in COMUNAS_NUBLE
    assert "Chillán Viejo" in COMUNAS_NUBLE
    assert "San Carlos" in COMUNAS_NUBLE
    assert "Coihueco" in COMUNAS_NUBLE
    assert "Bulnes" in COMUNAS_NUBLE
    assert "Quirihue" in COMUNAS_NUBLE
    assert "Yungay" in COMUNAS_NUBLE


def test_comunas_prioritarias_no_duplicates():
    """Verifica que las comunas prioritarias no tengan duplicados."""
    assert len(COMUNAS_PRIORITARIAS_DEFAULT) == len(set(COMUNAS_PRIORITARIAS_DEFAULT))


def test_find_comuna_and_region():
    """Prueba la resolución de comuna y región en textos habituales."""
    # Coincidencia directa
    comuna, region = find_comuna_and_region("Chillán, Región de Ñuble")
    assert comuna == "Chillán"
    assert region == "Ñuble"

    # Coincidencia con minúsculas y sin tildes
    comuna, region = find_comuna_and_region("san carlos, nuble")
    assert comuna == "San Carlos"
    assert region == "Ñuble"

    # Chillán Viejo
    comuna, region = find_comuna_and_region("Oferta presencial en Chillan Viejo")
    assert comuna == "Chillán Viejo"
    assert region == "Ñuble"

    # Otra región
    comuna, region = find_comuna_and_region("Concepción, Biobío")
    assert comuna == "Concepción"
    assert region == "Biobío"

    # Texto vacío
    comuna, region = find_comuna_and_region("")
    assert comuna is None
    assert region is None
