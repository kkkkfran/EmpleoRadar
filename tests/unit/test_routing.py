"""Pruebas unitarias para el enrutamiento de canales de EmpleoRadar.

Canal 1 (1561207531659985106): Informática general (Concepción, Ñuble, Remoto, Chile).
Canal 2 (1561217778722283613): Otros empleos en Chillán (Retail, Falabella, Ripley, Jumbo, Paris, sin título universitario).
"""

from unittest.mock import MagicMock

from app.bot.client import EmpleoRadarBot
from app.config import Settings
from app.jobs.models import JobPayload


def create_mock_bot() -> EmpleoRadarBot:
    settings = Settings(
        discord_bot_token="test_token",
        discord_owner_id=123456789,
        discord_channel_informatica_id=1561207531659985106,
        discord_channel_chillan_id=1561217778722283613,
    )
    repo = MagicMock()
    profile_service = MagicMock()
    app_service = MagicMock()
    source_registry = MagicMock()
    health_monitor = MagicMock()

    bot = EmpleoRadarBot(
        settings=settings,
        repository=repo,
        profile_service=profile_service,
        app_service=app_service,
        source_registry=source_registry,
        health_monitor=health_monitor,
    )
    return bot


def test_routing_it_job_concepcion():
    bot = create_mock_bot()
    job = JobPayload(
        source_name="Chiletrabajos",
        title="Ingeniero en Informática / Desarrollador Python",
        description="Desarrollo de microservicios y soporte a sistemas cloud.",
        region="Biobío",
        comuna="Concepción",
        url="https://chiletrabajos.cl/enc/1",
    )
    dest_channel = bot.get_destination_channel_id(job)
    assert dest_channel == 1561207531659985106


def test_routing_it_job_nuble():
    bot = create_mock_bot()
    job = JobPayload(
        source_name="Chiletrabajos",
        title="Soporte Técnico TI y Redes",
        description="Mantenimiento de computadores y cableado estructurado.",
        region="Ñuble",
        comuna="Chillán",
        url="https://chiletrabajos.cl/enc/2",
    )
    dest_channel = bot.get_destination_channel_id(job)
    # Informática tiene prioridad para canal informatica
    assert dest_channel == 1561207531659985106


def test_routing_chillan_retail_ropa():
    bot = create_mock_bot()
    job = JobPayload(
        source_name="Chiletrabajos",
        title="Asistente de Ventas y Organizador de Ropa",
        description="Atención a clientes y reposición de mercadería en tienda Falabella.",
        region="Ñuble",
        comuna="Chillán",
        url="https://chiletrabajos.cl/enc/3",
    )
    dest_channel = bot.get_destination_channel_id(job)
    assert dest_channel == 1561217778722283613


def test_routing_chillan_supermercado_reponedor():
    bot = create_mock_bot()
    job = JobPayload(
        source_name="Chiletrabajos",
        title="Reponedor de Supermercado Jumbo",
        description="Turnos rotativos, orden de pasillos y control de stock.",
        region="Ñuble",
        comuna="Chillán Viejo",
        url="https://chiletrabajos.cl/enc/4",
    )
    dest_channel = bot.get_destination_channel_id(job)
    assert dest_channel == 1561217778722283613


def test_routing_excludes_university_professional_roles():
    bot = create_mock_bot()
    job = JobPayload(
        source_name="Chiletrabajos",
        title="Médico Cirujano para Hospital",
        description="Atención médica general y de urgencias.",
        region="Ñuble",
        comuna="Chillán",
        url="https://chiletrabajos.cl/enc/5",
    )
    dest_channel = bot.get_destination_channel_id(job)
    # No va a Informática ni a Otros Empleos (requiere título médico universitario)
    assert dest_channel is None


def test_routing_other_city_non_it_ignored():
    bot = create_mock_bot()
    job = JobPayload(
        source_name="Chiletrabajos",
        title="Cajero para Restaurante",
        description="Manejo de caja y cuadratura.",
        region="Metropolitana",
        comuna="Santiago",
        url="https://chiletrabajos.cl/enc/6",
    )
    dest_channel = bot.get_destination_channel_id(job)
    assert dest_channel is None
