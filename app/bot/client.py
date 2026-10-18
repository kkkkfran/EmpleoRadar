"""Cliente principal del bot de Discord para EmpleoRadar."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from app.bot.commands.job_commands import EmpleoCog
from app.bot.embeds import create_job_card_embed
from app.bot.views.job_views import JobCardLayoutView, JobCardView
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
        from datetime import datetime

        logger.info(
            "✅ EmpleoRadar conectado como %s (ID: %d)", self.user, self.user.id if self.user else 0
        )
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="ofertas en Chillán e Informática",
        )
        await self.change_presence(activity=activity)

        # Iniciar de inmediato la detección y publicación de ofertas desde el 13 de octubre
        if self.scheduler_runner:
            logger.info(
                "🚀 Iniciando escaneo y publicación automática de vacantes desde el 13 de octubre..."
            )
            import asyncio

            asyncio.create_task(
                self.scheduler_runner.run_all_sources_now(since_date=datetime(2026, 10, 13))
            )

    def get_destination_channel_id(self, job: JobPayload) -> int | None:
        """Determina el canal específico de Discord según el tipo de oferta y ubicación.

        • Informática general -> Canal 1561207531659985106
        • Otros empleos dentro de Chillán (retail, tiendas, ropa, reponedor, etc.) -> Canal 1561217778722283613
        """
        import re

        title_lower = job.title.lower()
        desc_lower = (job.description or "").lower()
        text = f"{title_lower} {desc_lower}"

        # 1. Filtro estricto para oficios manuales/eléctricos/mecánicos no-IT
        non_it_trades = [
            "eléctrico", "electrico", "eléctrica", "electrica", "mecánico", "mecanico",
            "electromecánico", "electromecanico", "climatización", "climatizacion",
            "gasfiter", "gasfitería", "gasfiteria", "plomero", "soldador", "albañil",
            "carpintero", "pintor", "maestro mayor", "chofer", "conductor", "guardia",
            "aseo", "auxiliar de aseo", "manipuladora de alimentos"
        ]
        strict_it_in_title = [
            "informática", "informático", "informatico", "software", "desarrollador",
            "programador", "computación", "computacional", "ti", "devops", "cloud",
            "ciberseguridad", "base de datos", "bases de datos", "fullstack", "backend", "frontend"
        ]

        is_non_it_trade = any(
            re.search(r"\b" + re.escape(trade) + r"\b", title_lower) for trade in non_it_trades
        )
        has_strict_it_title = any(
            re.search(r"\b" + re.escape(it_w) + r"\b", title_lower) for it_w in strict_it_in_title
        )

        # 2. ¿Es oferta de Informática / Tecnología? -> Canal de Informática
        it_keywords = [
            "informática", "informatico", "informático", "computación", "computacional",
            "desarrollo", "desarrollador", "software", "programador", "programación",
            "backend", "frontend", "full stack", "fullstack", "web", "devops",
            "python", "java", "javascript", "typescript", "c#", ".net", "php", "golang",
            "sql", "base de datos", "bases de datos", "database", "redes", "networking",
            "telecomunicaciones", "soporte ti", "soporte técnico", "soporte computacional",
            "sistemas informáticos", "sistemas y computación", "ingeniero de sistemas",
            "ingeniería de sistemas", "analista de sistemas", "administrador de sistemas",
            "infraestructura", "cloud", "aws", "azure", "ciberseguridad", "seguridad informática",
            "qa", "testing", "ciencia de datos", "data science", "data engineer", "data analytics",
            "analista de datos", "tecnología", "tecnologias", "tecnologías"
        ]

        if (not is_non_it_trade or has_strict_it_title) and any(
            re.search(r"\b" + re.escape(kw) + r"\b", text) for kw in it_keywords
        ):
            return self.settings.discord_channel_informatica_id

        # 3. ¿Es oferta dentro de Chillán? (Retail, tiendas, ropa, reponedor, bodega, etc.)
        comuna_str = f"{job.comuna or ''} {job.location_raw or ''}".lower()
        if "chillan" in comuna_str or "chillán" in comuna_str:
            # Excluir profesiones que requieren título universitario estricto
            professional_exclude = [
                "médico", "medico", "abogado", "abogada", "psicólogo", "psicologa",
                "psicólogo/a", "enfermero", "enfermera", "enfermero/a", "odontólogo",
                "odontologo", "kinesiólogo", "kinesiologo", "químico farmacéutico"
            ]
            if any(
                re.search(r"\b" + re.escape(excl) + r"\b", title_lower)
                for excl in professional_exclude
            ):
                return None
            return self.settings.discord_channel_chillan_id

        # No califica para los canales seleccionados
        return None

    async def notify_new_job(
        self,
        job: JobPayload,
        match_result: JobMatchResult,
        job_id: int,
    ) -> None:
        """Envía una notificación al canal de Discord correspondiente usando Discord Components V2.

        NUNCA envía a mensaje privado (DM), respetando la directiva explícita del usuario.
        """
        try:
            channel_id = self.get_destination_channel_id(job)
            if not channel_id:
                logger.debug(
                    "La vacante #%d no coincide con los canales de destino configurados.", job_id
                )
                return

            target_channel = self.get_channel(channel_id) or await self.fetch_channel(channel_id)
            if not target_channel or not isinstance(
                target_channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)
            ):
                logger.warning(
                    "No se pudo acceder al canal de destino %s para la oferta #%d.",
                    channel_id,
                    job_id,
                )
                return

            try:
                # Usar Discord Components V2 (LayoutView con Separator)
                layout_view = JobCardLayoutView(
                    job=job,
                    match_result=match_result,
                    job_id=job_id,
                    owner_id=self.owner_id,
                    application_service=self.app_service,
                    repository=self.repo,
                )
                await target_channel.send(view=layout_view)
            except Exception as v2_err:
                logger.warning(
                    "Fallo al enviar con Components V2 (aplicando fallback clásico): %s", v2_err
                )
                embed = create_job_card_embed(job, match_result=match_result, job_id=job_id)
                view = JobCardView(
                    job_id=job_id,
                    job_url=job.url,
                    owner_id=self.owner_id,
                    application_service=self.app_service,
                    repository=self.repo,
                )
                await target_channel.send(
                    content="🔔 **¡Nueva oportunidad laboral detectada!**",
                    embed=embed,
                    view=view,
                )

            logger.info(
                "Notificación publicada en #%s (%s) para oferta #%d: %s",
                getattr(target_channel, "name", "canal"),
                channel_id,
                job_id,
                job.title,
            )
        except Exception as e:
            logger.error("Error al publicar notificación para oferta #%d: %s", job_id, e)

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
