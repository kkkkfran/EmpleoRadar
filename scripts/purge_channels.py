"""Script para purgar/vaciar los canales de alertas en Discord y resetear notificaciones."""

from __future__ import annotations

import asyncio
import os

import discord
from dotenv import load_dotenv

from app.config import get_settings
from app.database.repository import Database, Repository

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_IT = int(os.getenv("DISCORD_CHANNEL_INFORMATICA_ID", "1561207531659985106"))
CHANNEL_CHI = int(os.getenv("DISCORD_CHANNEL_CHILLAN_ID", "1561217778722283613"))

intents = discord.Intents.default()
client = discord.Client(intents=intents)


async def reset_database_notifications() -> None:
    """Resetea el estado de notificaciones en la base de datos."""
    try:
        settings = get_settings()
        db = Database(settings.database_url)
        repo = Repository(db)
        count = await repo.reset_all_notifications()
        print(f"[OK] Se resetearon {count} ofertas en base de datos para reenvio.")
        await db.close()
    except Exception as e:
        print(f"Nota/Advertencia reseteando base de datos: {e}")


@client.event
async def on_ready() -> None:
    print(f"Conectado como {client.user} (ID: {client.user.id})")
    for cid in [CHANNEL_IT, CHANNEL_CHI]:
        try:
            channel = client.get_channel(cid) or await client.fetch_channel(cid)
            ch_name = getattr(channel, "name", str(cid))
            print(f"Iniciando purga total de canal #{ch_name} ({cid})...")
            total_deleted = 0
            while True:
                deleted = await channel.purge(limit=100)
                if not deleted:
                    break
                total_deleted += len(deleted)
                print(f"  Borrados {total_deleted} mensajes...")
                await asyncio.sleep(0.5)
            print(f"[OK] Canal #{ch_name} completamente limpio ({total_deleted} mensajes eliminados).")
        except Exception as e:
            print(f"Error al limpiar canal {cid}: {e}")

    await reset_database_notifications()
    await client.close()


if __name__ == "__main__":
    client.run(TOKEN)

