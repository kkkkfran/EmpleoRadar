"""Lógica de deduplicación y generación de huellas digitales de ofertas laborales."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from app.jobs.models import JobPayload
from app.jobs.regions_data import normalize_text_match

# Parámetros de rastreo que deben eliminarse al normalizar URLs
_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "ref",
    "referer",
    "source",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}


def normalize_job_url(url: str) -> str:
    """Elimina parámetros de seguimiento y normaliza protocolo y dominio de la URL."""
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())
        query_dict = parse_qs(parsed.query, keep_blank_values=False)
        # Filtrar parámetros tracking
        filtered_query = {k: v for k, v in query_dict.items() if k.lower() not in _TRACKING_PARAMS}
        new_query = urlencode(filtered_query, doseq=True)
        # Quitar barras finales en path
        new_path = parsed.path.rstrip("/")
        normalized = urlunparse(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                new_path,
                parsed.params,
                new_query,
                "",  # Quitar fragmento #
            )
        )
        return normalized
    except Exception:
        return url.strip()


def generate_dedup_hash(
    company: str | None,
    title: str,
    comuna: str | None = None,
    region: str | None = None,
    source_name: str | None = None,
    external_id: str | None = None,
    url: str | None = None,
) -> str:
    """Genera una huella SHA-256 única y determinista para deduplicación.

    Estrategia de dos niveles:
    1. Si hay external_id estable y source_name, genera clave primaria de origen.
    2. Genera firma de contenido basada en empresa normalizada, título normalizado y ubicación
       para detectar vacantes cruzadas entre distintos portales.
    """
    norm_title = normalize_text_match(title)
    # Limpiar palabras vacías comunes en títulos
    norm_title = re.sub(r"\b(se busca|requiere|importante|empresa)\b", "", norm_title).strip()
    norm_title = re.sub(r"\s+", " ", norm_title)

    norm_company = normalize_text_match(company or "confidencial")
    norm_comuna = normalize_text_match(comuna or "")
    norm_region = normalize_text_match(region or "")

    # Combinación canónica
    canonical = f"{norm_company}|{norm_title}|{norm_comuna}|{norm_region}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_job_fingerprint(job: JobPayload) -> str:
    """Calcula y asigna el hash de deduplicación al JobPayload."""
    h = generate_dedup_hash(
        company=job.company,
        title=job.title,
        comuna=job.comuna,
        region=job.region,
        source_name=job.source_name,
        external_id=job.external_id,
        url=job.url,
    )
    job.dedup_hash = h
    return h
