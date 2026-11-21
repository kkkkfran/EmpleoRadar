"""Envía una única vista previa Components V2 usando una oferta ya registrada."""

import asyncio

import discord

from app.bot.views.job_views import create_job_card_layout
from app.config import get_settings
from app.database.migrations.runner import run_migrations
from app.database.models import WorkModality
from app.database.repository import Database, Repository
from app.jobs.matching import evaluate_job_match
from app.jobs.models import JobPayload
from app.jobs.routing import route_job
from app.profile.preferences import criteria_from_db_preferences


async def main() -> None:
    settings = get_settings()
    database = Database(settings.database_url)
    await database.create_tables()
    await run_migrations(database)
    repo = Repository(database)
    jobs = await repo.get_recent_jobs(limit=100)
    owner = await repo.get_or_create_owner(settings.discord_owner_id)
    preferences = await repo.get_or_create_preferences(owner.id)
    criteria = criteria_from_db_preferences(preferences)
    job = None
    match = None
    for candidate in jobs:
        candidate.modality = WorkModality(candidate.modality)
        fields = {
            name: getattr(candidate, name)
            for name in JobPayload.model_fields
            if name not in {"source_name", "location_raw", "raw_data"}
            and hasattr(candidate, name)
        }
        payload = JobPayload(
            **fields,
            source_name=candidate.source.name if candidate.source else "Fuente",
            location_raw=candidate.location,
        )
        candidate_match = evaluate_job_match(payload, criteria)
        if (
            not candidate_match.is_excluded
            and candidate_match.score >= criteria.min_score_notify
            and route_job(
                payload,
                settings.discord_channel_informatica_id,
                settings.discord_channel_chillan_id,
            )
            == settings.discord_channel_informatica_id
        ):
            job = candidate
            match = candidate_match
            break
    if job is None:
        await database.close()
        raise RuntimeError("No hay ofertas TI compatibles registradas para construir la prueba")

    job.title = f"[PRUEBA VISUAL] {job.title}"
    job.description = (
        "Este es el formato nuevo de EmpleoRadar. Los botones cambian y guardan el estado "
        "sin borrar la publicación.\n\n" + (job.description or "")
    )
    client = discord.Client(intents=discord.Intents.default())

    @client.event
    async def on_ready() -> None:
        channel = client.get_channel(settings.discord_channel_informatica_id)
        if channel is None:
            channel = await client.fetch_channel(settings.discord_channel_informatica_id)
        message = await channel.send(
            view=create_job_card_layout(job, match_result=match, job_id=job.id)
        )
        print(f"Mensaje Components V2 de prueba enviado: {message.id}")
        await client.close()

    try:
        await client.start(settings.discord_bot_token)
    finally:
        await database.close()


if __name__ == "__main__":
    asyncio.run(main())
