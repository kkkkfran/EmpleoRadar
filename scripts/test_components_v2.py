import os

import discord
from discord.ui import ActionRow, Button, LayoutView, Separator, TextDisplay
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_IT = int(os.getenv("DISCORD_CHANNEL_INFORMATICA_ID", "1561207531659985106"))

client = discord.Client(intents=discord.Intents.default())

@client.event
async def on_ready():
    channel = client.get_channel(CHANNEL_IT) or await client.fetch_channel(CHANNEL_IT)
    print("Testing Components V2 LayoutView in channel:", channel)

    view = LayoutView()
    view.add_item(TextDisplay("### 💼 Desarrollador Full Stack Python / React\n**Empresa:** Tech Soluciones • **Ubicación:** Concepción, Biobío\n**Modalidad:** Remoto • **Contrato:** Indefinido"))
    view.add_item(Separator(visible=True, spacing=discord.SeparatorSpacing.small))
    view.add_item(TextDisplay("💰 **Remuneración:** $1.800.000 - $2.400.000 Líquido\n⏳ **Experiencia requerida:** 2+ años en FastAPI, React y PostgreSQL\n🎯 **Compatibilidad:** 92/100 (Alta prioridad en Concepción y Python)"))
    view.add_item(Separator(visible=True, spacing=discord.SeparatorSpacing.small))
    view.add_item(TextDisplay("-# Fuente: ChileTrabajos | ID #999 • EmpleoRadar • 18-10-2026 01:45"))

    row = ActionRow(
        Button(label="Ver oferta", style=discord.ButtonStyle.link, url="https://chiletrabajos.cl"),
        Button(label="Preparar postulación", style=discord.ButtonStyle.primary, custom_id="test_postular"),
        Button(label="Guardar oferta", style=discord.ButtonStyle.secondary, custom_id="test_guardar")
    )
    view.add_item(row)

    try:
        msg = await channel.send(view=view)
        print("Components V2 message sent successfully! ID:", msg.id)
    except Exception as e:
        print("Error sending Components V2:", e)

    await client.close()

if __name__ == "__main__":
    client.run(TOKEN)
