"""Cliente principal del bot de Discord para EmpleoRadar."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands

from app.bot.commands.job_commands import EmpleoCog
from app.bot.views.job_views import AppliedButton, DismissedButton, create_job_card_layout
from app.config import Settings
from app.database.repository import Repository
from app.jobs.models import JobMatchResult, JobPayload
from app.jobs.routing import route_job

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
        self.add_dynamic_items(AppliedButton, DismissedButton)

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
            name="ofertas en Chillán e Informática",
        )
        await self.change_presence(activity=activity)

    def get_destination_channel_id(self, job: JobPayload) -> int | None:
        """Determina el canal específico de Discord según el tipo de oferta y ubicación.

        • Informática general -> Canal 1561207531659985106
        • Otros empleos dentro de Chillán (retail, tiendas, ropa, reponedor, etc.) -> Canal 1561217778722283613
        """
        return route_job(
            job,
            self.settings.discord_channel_informatica_id,
            self.settings.discord_channel_chillan_id,
        )

    async def notify_new_job(
        self,
        job: JobPayload,
        match_result: JobMatchResult,
        job_id: int,
    ) -> int | None:
        """Envía una notificación al canal de Discord correspondiente usando Discord Components V2.

        NUNCA envía a mensaje privado (DM), respetando la directiva explícita del usuario.
        Retorna el ID del mensaje enviado, o None si no se pudo enviar.
        """
        try:
            if not self.is_ready():
                return None
            if job.published_at:
                published = job.published_at
                if published.tzinfo is None:
                    published = published.replace(tzinfo=UTC)
                now = datetime.now(UTC)
                if not now - timedelta(days=self.settings.recovery_days) <= published <= now:
                    logger.info("Aviso #%d omitido: publicación fuera de la ventana reciente.", job_id)
                    return None
            channel_id = self.get_destination_channel_id(job)
            if not channel_id:
                logger.debug(
                    "La vacante #%d no coincide con los canales de destino configurados.", job_id
                )
                return None

            target_channel = self.get_channel(channel_id) or await self.fetch_channel(channel_id)
            if not target_channel or not isinstance(
                target_channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)
            ):
                logger.warning(
                    "No se pudo acceder al canal de destino %s para la oferta #%d.",
                    channel_id,
                    job_id,
                )
                return None

            view = create_job_card_layout(job, match_result=match_result, job_id=job_id)
            message = await target_channel.send(
                view=view, allowed_mentions=discord.AllowedMentions.none()
            )

            logger.info(
                "Notificación publicada en #%s (%s) para oferta #%d: %s",
                getattr(target_channel, "name", "canal"),
                channel_id,
                job_id,
                job.title,
            )
            return message.id
        except Exception as e:
            logger.error("Error al publicar notificación para oferta #%d: %s", job_id, e)
            return None

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
