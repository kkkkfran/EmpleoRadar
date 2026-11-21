"""Preview or reset one configured EmpleoRadar Discord channel, with an archive."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import discord
from sqlalchemy import update

from app.config import get_settings
from app.database.models import Job
from app.database.repository import Database


def message_record(message: discord.Message) -> dict:
    return {
        "id": message.id,
        "channel_id": message.channel.id,
        "guild_id": message.guild.id if message.guild else None,
        "author_id": message.author.id,
        "created_at": message.created_at.isoformat(),
        "content": message.content,
        "embeds": [embed.to_dict() for embed in message.embeds],
        "components": [component.to_dict() for component in message.components],
        "attachments": [
            {"filename": item.filename, "url": item.url, "size": item.size}
            for item in message.attachments
        ],
    }


async def main(args: argparse.Namespace) -> None:
    settings = get_settings()
    allowed_channel_ids = {
        settings.discord_channel_informatica_id,
        settings.discord_channel_chillan_id,
    }
    if args.channel_id not in allowed_channel_ids:
        raise SystemExit(
            "Refusing: channel ID is not one of EmpleoRadar's configured alert channels."
        )

    executing = args.execute
    if executing and (
        args.confirm_channel_id != args.channel_id or args.expected_message_count is None
    ):
        raise SystemExit(
            "Execution requires --confirm-channel-id matching --channel-id and "
            "--expected-message-count from the reviewed preview."
        )

    client = discord.Client(intents=discord.Intents.none())
    db = Database(settings.database_url)
    try:
        await client.login(settings.discord_bot_token)
        channel = await client.fetch_channel(args.channel_id)
        if not isinstance(channel, discord.TextChannel):
            raise SystemExit("Refusing: the configured destination is not a guild text channel.")

        guild = await client.fetch_guild(channel.guild.id)
        guild._roles = {role.id: role for role in await guild.fetch_roles()}
        channel.guild = guild
        member = await guild.fetch_member(client.user.id)
        permissions = channel.permissions_for(member)
        if not permissions.view_channel or not permissions.read_message_history:
            raise SystemExit("Refusing: bot needs View Channel and Read Message History.")
        if executing and not permissions.manage_messages:
            raise SystemExit("Refusing: bot needs Manage Messages to empty this channel.")

        messages = [message async for message in channel.history(limit=None, oldest_first=True)]
        configured_role = (
            "Informática"
            if channel.id == settings.discord_channel_informatica_id
            else "Chillán / Otros empleos"
        )
        summary = {
            "guild": guild.name,
            "guild_id": guild.id,
            "channel": channel.name,
            "channel_id": channel.id,
            "configured_role": configured_role,
            "is_empleoradar_publication_channel": channel.id in allowed_channel_ids,
            "message_count": len(messages),
            "oldest_message_at": messages[0].created_at.isoformat() if messages else None,
            "newest_message_at": messages[-1].created_at.isoformat() if messages else None,
            "bot_permissions": {
                "view_channel": permissions.view_channel,
                "read_message_history": permissions.read_message_history,
                "manage_messages": permissions.manage_messages,
                "send_messages": permissions.send_messages,
            },
            "start_date_inclusive": args.start_date,
            "mode": "execute" if executing else "preview",
        }
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        if not executing:
            return
        if len(messages) != args.expected_message_count:
            raise SystemExit(
                f"Refusing: message count changed; expected {args.expected_message_count}, "
                f"found {len(messages)}. Review a fresh preview."
            )

        archive_dir = Path(args.archive_dir) if args.archive_dir else settings.backup_path
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / (
            f"discord-channel-{channel.id}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.jsonl"
        )
        with archive_path.open("x", encoding="utf-8") as archive:
            for message in messages:
                archive.write(json.dumps(message_record(message), ensure_ascii=False) + "\n")
        print(f"ARCHIVE {archive_path}", flush=True)

        # Discord only permits bulk deletion for messages less than 14 days old.
        bulk_cutoff = datetime.now(UTC) - timedelta(days=14)
        recent = [message for message in messages if message.created_at > bulk_cutoff]
        older = [message for message in messages if message.created_at <= bulk_cutoff]
        deleted = 0
        for offset in range(0, len(recent), 100):
            batch = recent[offset : offset + 100]
            if len(batch) == 1:
                await batch[0].delete()
            elif batch:
                await channel.delete_messages(batch, reason="EmpleoRadar channel reset (confirmed)")
            deleted += len(batch)
        for message in older:
            await message.delete()
            deleted += 1
        print(f"DELETED {deleted} messages from channel {channel.id}", flush=True)

        start_cutoff = datetime.combine(
            datetime.strptime(args.start_date, "%Y-%m-%d").date(), datetime.min.time()
        )
        async with db.session() as session:
            reset_jobs = 0
            for message in messages:
                result = await session.execute(
                    update(Job)
                    .where(
                        Job.notification_message_id == message.id,
                        Job.published_at >= start_cutoff,
                        Job.user_decision == "pending",
                        Job.status == "activa",
                    )
                    .values(
                        notified=False,
                        notification_message_id=None,
                        notification_eligible=True,
                    )
                )
                reset_jobs += result.rowcount or 0
            await session.commit()
        print(f"RESET {reset_jobs} pending active job notifications; archive retained", flush=True)
        remaining = sum(1 async for _ in channel.history(limit=None))
        print(f"REMAINING {remaining} messages in channel {channel.id}", flush=True)
        print("Restart the bot service to resume automatic publication.", flush=True)
    finally:
        await client.close()
        await db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel-id", required=True, type=int)
    parser.add_argument("--start-date", default="2026-11-16")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-channel-id", type=int)
    parser.add_argument("--expected-message-count", type=int)
    parser.add_argument("--archive-dir")
    arguments = parser.parse_args()
    requested_start_date = datetime.strptime(arguments.start_date, "%Y-%m-%d").date()
    if requested_start_date < datetime(2026, 11, 16).date():
        raise SystemExit("--start-date cannot be earlier than 2026-11-16.")
    try:
        asyncio.run(main(arguments))
    except discord.LoginFailure as exc:
        raise SystemExit(
            "Discord rejected the configured bot token; no channel changes were made."
        ) from exc
