"""Script para purgar/vaciar los canales de alertas en Discord."""
import os

import discord
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_IT = int(os.getenv("DISCORD_CHANNEL_INFORMATICA_ID", "1561207531659985106"))
CHANNEL_CHI = int(os.getenv("DISCORD_CHANNEL_CHILLAN_ID", "1561217778722283613"))

intents = discord.Intents.default()
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"Conectado como {client.user} (ID: {client.user.id})")
    for cid in [CHANNEL_IT, CHANNEL_CHI]:
        try:
            channel = client.get_channel(cid) or await client.fetch_channel(cid)
            print(f"Limpiando canal #{getattr(channel, 'name', cid)} ({cid})...")
            # Purge up to 500 messages
            deleted = await channel.purge(limit=500)
            print(f"Eliminados {len(deleted)} mensajes en #{getattr(channel, 'name', cid)}")
        except Exception as e:
            print(f"Error al limpiar canal {cid}: {e}")
    await client.close()

if __name__ == "__main__":
    client.run(TOKEN)
