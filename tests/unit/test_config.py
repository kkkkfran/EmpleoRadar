"""Validation for runtime-only BNE settings and the publication boundary."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.sources.registry import SourceRegistry


def test_bne_postulante_id_is_configurable_and_wired_to_source() -> None:
    settings = Settings(
        _env_file=None,
        discord_bot_token="test-token",
        discord_owner_id=1,
        bne_postulante_id="10660398",
    )
    registry = SourceRegistry(repository=None, bne_postulante_id=settings.bne_postulante_id)
    source = registry.get_source("BNE")

    assert settings.bne_postulante_id == "10660398"
    assert source is not None
    assert source.build_offer_url("1601391") == (
        "https://www.bne.cl/ofertas/1601391?idPostulante=10660398"
    )


def test_publication_date_cannot_be_configured_before_requested_boundary() -> None:
    settings = Settings(
        _env_file=None,
        discord_bot_token="test-token",
        discord_owner_id=1,
    )
    assert settings.publication_start_date == date(2026, 11, 16)

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            discord_bot_token="test-token",
            discord_owner_id=1,
            publication_start_date="2026-11-15",
        )
