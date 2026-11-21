"""Maintenance: preview or rebuild both channels for an explicit publication window."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

import aiohttp
import discord
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.bot.views.job_views import create_job_card_layout
from app.config import get_settings
from app.database.models import Job
from app.database.repository import Database, Repository
from app.jobs.matching import evaluate_job_match
from app.jobs.routing import route_job
from app.profile.preferences import criteria_from_db_preferences
from app.scheduler.runner import JobSchedulerRunner
from app.sources.registry import SourceRegistry


async def main(args):
    settings = get_settings()
    db = Database(settings.database_url)
    repo = Repository(db)
    client = discord.Client(intents=discord.Intents.default())
    try:
        registry = SourceRegistry(repo)
        await registry.sync_with_database()
        runner = JobSchedulerRunner(repo, registry, settings.discord_owner_id)
        async with aiohttp.ClientSession() as session:
            runner._session = session
            await runner._dispatch_jobs_for_sources(
                [s for s in registry.get_active_sources() if s.name != "BNE"],
            )
        async with db.session() as session:
            jobs = (await session.execute(
                select(Job).options(selectinload(Job.source))
                .where(Job.published_at >= args.start, Job.published_at < args.end)
                .order_by(Job.published_at, Job.id)
            )).scalars().all()
            unknown_dates = (await session.execute(
                select(Job.id).where(Job.published_at.is_(None))
            )).scalars().all()
        owner = await repo.get_or_create_owner(settings.discord_owner_id)
        criteria = criteria_from_db_preferences(await repo.get_or_create_preferences(owner.id))
        channel_ids = [settings.discord_channel_informatica_id, settings.discord_channel_chillan_id]
        assert len(set(channel_ids)) == 2, "Expected two distinct channels"
        planned = []
        for job in jobs:
            payload = runner._payload_from_job(job)
            channel_id = route_job(payload, *channel_ids)
            if not channel_id:
                continue
            match = evaluate_job_match(payload, criteria)
            if match.is_excluded or match.score < criteria.min_score_notify:
                continue
            view = create_job_card_layout(
                job, match, job.id, decision=job.user_decision
            )
            view.to_components()
            planned.append((job, channel_id, view))
        print(json.dumps({"eligible": len(planned), "by_channel": {
            str(cid): sum(c == cid for _, c, _ in planned) for cid in channel_ids
        }, "excluded_unknown_publication_date": len(unknown_dates)}), flush=True)
        await client.login(settings.discord_bot_token)
        channels = {cid: await client.fetch_channel(cid) for cid in channel_ids}
        for channel in channels.values():
            guild = await client.fetch_guild(channel.guild.id)
            guild._roles = {role.id: role for role in await guild.fetch_roles()}
            channel.guild = guild
            member = await guild.fetch_member(client.user.id)
            permissions = channel.permissions_for(member)
            assert all(getattr(permissions, p) for p in (
                "view_channel", "read_message_history", "manage_messages", "send_messages"
            )), f"Missing permissions in {channel.id}"
            print(f"CHANNEL {channel.id} {channel.name}", flush=True)
        if not args.execute:
            return
        if not planned:
            raise RuntimeError("No eligible jobs; refusing to empty channels")
        backup = Path(args.archive)
        backup.mkdir(parents=True, exist_ok=False)
        # Archive both histories before deleting anything.
        for cid, channel in channels.items():
            with (backup / f"{cid}.jsonl").open("w", encoding="utf-8") as out:
                async for message in channel.history(limit=None, oldest_first=True):
                    out.write(json.dumps({"id": message.id, "author_id": message.author.id,
                        "content": message.content, "embeds": [e.to_dict() for e in message.embeds],
                        "components": [c.to_dict() for c in message.components],
                        "attachments": [a.url for a in message.attachments]}, ensure_ascii=False) + "\n")
        for cid, channel in channels.items():
            deleted = 0
            while True:
                batch = await channel.purge(limit=100)
                if not batch:
                    break
                deleted += len(batch)
                print(f"DELETED {cid} {deleted}", flush=True)
            print(f"EMPTY {cid}", flush=True)
        async with db.session() as session:
            await session.execute(update(Job).values(notification_message_id=None))
            await session.commit()
        counts = dict.fromkeys(channel_ids, 0)
        for job, cid, view in planned:
            message = await channels[cid].send(view=view, allowed_mentions=discord.AllowedMentions.none())
            await repo.mark_job_notified(job.id, message.id)
            counts[cid] += 1
            print(f"PUBLISHED {job.id} {cid} {message.id}", flush=True)
            await asyncio.sleep(0.8)
        print("COMPLETE " + json.dumps(counts), flush=True)
    finally:
        await client.close()
        await db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=datetime.fromisoformat, required=True)
    parser.add_argument("--end", type=datetime.fromisoformat, required=True,
                        help="Exclusive end of publication window")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--archive", default="/app/data/channel-rebuild-20261030")
    asyncio.run(main(parser.parse_args()))
