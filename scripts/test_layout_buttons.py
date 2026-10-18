import asyncio
import os

import discord
from discord.ui import ActionRow, Button, LayoutView, Separator, TextDisplay
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_IT = int(os.getenv("DISCORD_CHANNEL_INFORMATICA_ID", "1561207531659985106"))

class CardLayout(LayoutView):
    def __init__(self, job_title, url):
        super().__init__(timeout=60)
        self.job_title = job_title
        self.url = url

        self.add_item(TextDisplay(f"### 💼 {job_title}\n**Empresa:** Empresa Test • **Ubicación:** Chillán"))
        self.add_item(Separator(visible=True, spacing=discord.SeparatorSpacing.small))
        self.add_item(TextDisplay("💰 **Remuneración:** $1.500.000 Líquido\n🎯 **Compatibilidad:** 85/100"))
        self.add_item(Separator(visible=True, spacing=discord.SeparatorSpacing.small))
        self.add_item(TextDisplay("-# Fuente: BNE • EmpleoRadar"))

        btn_apply = Button(label="Preparar postulación", style=discord.ButtonStyle.primary)
        btn_apply.callback = self.on_apply

        btn_link = Button(label="Ver oferta", style=discord.ButtonStyle.link, url=url)

        self.add_item(ActionRow(btn_apply, btn_link))

    async def on_apply(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"¡Botón presionado para: {self.job_title}!", ephemeral=True)

client = discord.Client(intents=discord.Intents.default())

@client.event
async def on_ready():
    channel = client.get_channel(CHANNEL_IT) or await client.fetch_channel(CHANNEL_IT)
    view = CardLayout("Ingeniero en Informática Test", "https://www.bne.cl")
    msg = await channel.send(view=view)
    print("Sent test LayoutView with ID:", msg.id)
    await asyncio.sleep(2)
    await msg.delete()
    print("Test message cleaned up successfully.")
    await client.close()

if __name__ == "__main__":
    client.run(TOKEN)
