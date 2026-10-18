"""Cliente principal del bot de Discord para EmpleoRadar."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from app.bot.commands.job_commands import EmpleoCog
from app.bot.embeds import create_job_card_embed
from app.bot.views.job_views import JobCardView
from app.config import Settings
from app.database.repository import Repository
from app.jobs.models import JobMatchResult, JobPayload

logger = logging.getLogger(__name__)


class EmpleoRadarBot(commands.Bot):
    """Bot de Discord para búsqueda y postulación personalizada a empleos."""

    def __init__(
        self,
        settings: Settings,
        repository: Repository,
        profile_service,
        app_service,
        source_registry,
        health_monitor,
    ) -> None:
        intents = discord.Intents.default()
        intents.members = False
        intents.message_content = False

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
        )
        self.settings = settings
        self.repo = repository
        self.profile_service = profile_service
        self.app_service = app_service
        self.source_registry = source_registry
        self.health_monitor = health_monitor
        self.scheduler_runner = None  # Asignado en bootstrap
        self.owner_id = settings.discord_owner_id

    async def setup_hook(self) -> None:
        """Inicializa extensiones y sincroniza comandos de aplicación."""
        logger.info("Configurando EmpleoRadarBot y comandos slash...")
        cog = EmpleoCog(self)
        await self.add_cog(cog)

        # Sincronización de comandos (por servidor si está definido, o global)
        if self.settings.discord_guild_id:
            guild = discord.Object(id=self.settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info(
                "Sincronizados %d comandos en el servidor %d.",
                len(synced),
                self.settings.discord_guild_id,
            )
        else:
            synced = await self.tree.sync()
            logger.info("Sincronizados %d comandos globales de Discord.", len(synced))

    async def on_ready(self) -> None:
        """Callback ejecutado cuando el bot se conecta satisfactoriamente a Discord."""
        logger.info(
            "✅ EmpleoRadar conectado como %s (ID: %d)", self.user, self.user.id if self.user else 0
        )
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="ofertas laborales en Ñuble",
        )
        await self.change_presence(activity=activity)

    async def notify_new_job(
        self,
        job: JobPayload,
        match_result: JobMatchResult,
        job_id: int,
    ) -> None:
        """Envía una notificación privada de nueva vacante al propietario por mensaje directo."""
        try:
            owner = await self.fetch_user(self.owner_id)
            if not owner:
                logger.warning(
                    "No se pudo obtener el usuario propietario con ID %s.", self.owner_id
                )
                return

            embed = create_job_card_embed(job, match_result=match_result, job_id=job_id)
            view = JobCardView(
                job_id=job_id,
                job_url=job.url,
                owner_id=self.owner_id,
                application_service=self.app_service,
                repository=self.repo,
            )

            dm_channel = owner.dm_channel or await owner.create_dm()
            await dm_channel.send(
                content="🔔 **¡Nueva vacante relevante detectada para tu perfil!**",
                embed=embed,
                view=view,
            )
            logger.info(
                "Notificación enviada al propietario para oferta #%d: %s", job_id, job.title
            )
        except Exception as e:
            logger.error(
                "Fallo al enviar notificación por MD al propietario (%s): %s", self.owner_id, e
            )

    async def on_tree_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Manejo global de errores en comandos slash."""
        if isinstance(error, app_commands.CheckFailure):
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "⛔ No tienes autorización para ejecutar este comando.",
                    ephemeral=True,
                )
        else:
            logger.exception(
                "Error en comando slash '%s': %s",
                interaction.command.name if interaction.command else "desconocido",
                error,
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Ocurrió un error inesperado al procesar la solicitud.",
                    ephemeral=True,
                )
