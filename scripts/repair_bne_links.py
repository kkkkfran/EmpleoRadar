"""Repair published BNE buttons only after verifying the exact public offer code."""

import asyncio
import json
import re

import aiohttp
import discord
from sqlalchemy import select

from app.config import get_settings
from app.database.models import Job, JobSource
from app.database.repository import Database, Repository
from app.sources.bne import BNESource


async def main():
    settings = get_settings()
    db = Database(settings.database_url)
    repo = Repository(db)
    source = BNESource(postulante_id=settings.bne_postulante_id)
    try:
        async with db.session() as session:
            jobs = (await session.execute(select(Job).join(JobSource).where(
                JobSource.name == "BNE", Job.notification_message_id.is_not(None)
            ))).scalars().all()
        async with discord.Client(intents=discord.Intents.default()) as client, aiohttp.ClientSession() as http:
            await client.login(settings.discord_bot_token)
            channels = [await client.fetch_channel(cid) for cid in (
                settings.discord_channel_informatica_id, settings.discord_channel_chillan_id
            )]
            fixed = 0
            for job in jobs:
                match = re.search(r"['\"]id['\"]\s*:\s*(\d+)", job.raw_data or "")
                if not match:
                    raise RuntimeError(f"No numeric BNE ID for job {job.id}")
                offer_id = match[1]
                detail = json.loads(await source.request_get(
                    http, f"https://www.bne.cl/api/ofertas/publica/{offer_id}"
                ))
                if detail.get("codigoOferta") != job.external_id:
                    raise RuntimeError(f"BNE code mismatch for job {job.id}")
                url = source.build_offer_url(offer_id)
                message = None
                for channel in channels:
                    try:
                        message = await channel.fetch_message(job.notification_message_id)
                        break
                    except discord.NotFound:
                        continue
                if message is None:
                    raise RuntimeError(f"Published message missing for job {job.id}")
                view = discord.ui.LayoutView.from_message(message, timeout=None)
                changed = 0
                for item in view.walk_children():
                    if isinstance(item, discord.ui.Button) and item.url == job.url:
                        item.url = url
                        changed += 1
                if not changed:
                    raise RuntimeError(f"Expected BNE button missing for job {job.id}")
                await message.edit(view=view, allowed_mentions=discord.AllowedMentions.none())
                await repo.update_job(job.id, url=url)
                confirmed = await message.channel.fetch_message(message.id)
                assert any(isinstance(item, discord.ui.Button) and item.url == url
                           for item in discord.ui.LayoutView.from_message(confirmed).walk_children())
                fixed += 1
                print(f"REPAIRED job={job.id} message={message.id} url={url}", flush=True)
            print(f"COMPLETE repaired={fixed}", flush=True)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
