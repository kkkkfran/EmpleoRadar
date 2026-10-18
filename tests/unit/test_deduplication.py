"""Pruebas unitarias para deduplicación y hashing de ofertas."""

from app.jobs.deduplication import generate_dedup_hash, normalize_job_url


def test_normalize_job_url():
    url = "https://www.chiletrabajos.cl/oferta/123/?utm_source=facebook&utm_campaign=winter&ref=share#detalles"
    norm = normalize_job_url(url)
    assert "utm_source" not in norm
    assert "utm_campaign" not in norm
    assert "ref" not in norm
    assert "#detalles" not in norm
    assert norm == "https://www.chiletrabajos.cl/oferta/123"


def test_dedup_hash_stability():
    h1 = generate_dedup_hash("Tech Corp", "Desarrollador Python", "Chillán", "Ñuble")
    h2 = generate_dedup_hash("Tech Corp", "Desarrollador Python", "Chillán", "Ñuble")
    assert h1 == h2
    assert len(h1) == 64  # SHA-256


def test_dedup_hash_cross_portal_detection():
    # Misma vacante publicada con pequeñas diferencias en portales distintos
    h1 = generate_dedup_hash("Empresa Alfa", "Se busca Desarrollador Backend", "Chillán", "Ñuble")
    h2 = generate_dedup_hash("Empresa Alfa", "Desarrollador Backend", "Chillán", "Ñuble")
    assert h1 == h2


def test_different_jobs_do_not_collide():
    h1 = generate_dedup_hash("Empresa Alfa", "Desarrollador Backend", "Chillán", "Ñuble")
    h2 = generate_dedup_hash("Empresa Alfa", "Soporte Técnico TI", "Chillán", "Ñuble")
    assert h1 != h2
