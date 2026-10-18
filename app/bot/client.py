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

        # 1. Filtro estricto para oficios manuales/minería/eléctricos/mecánicos no-IT
        non_it_trades = [
            "eléctrico", "electrico", "eléctrica", "electrica", "mecánico", "mecanico",
            "electromecánico", "electromecanico", "climatización", "climatizacion",
            "gasfiter", "gasfitería", "gasfiteria", "plomero", "soldador", "albañil",
            "carpintero", "pintor", "maestro mayor", "chofer", "conductor", "guardia",
            "aseo", "auxiliar de aseo", "manipuladora de alimentos",
            "geólogo", "geologo", "geología", "geologia", "minero", "minera",
            "minería", "mineria", "metalúrgico", "metalurgico", "sondaje", "perforista", "topógrafo", "topografo"
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
        it_title_keywords = [
            "informática", "informatico", "informático", "computación", "computacional",
            "desarrollador", "desarrollo de software", "desarrollo web", "desarrollo backend",
            "desarrollo frontend", "desarrollo full stack", "desarrollo fullstack",
            "software", "programador", "programación", "backend", "frontend",
            "full stack", "fullstack", "web developer", "devops", "cloud", "ciberseguridad",
            "seguridad informática", "qa", "qa automation", "tester", "testing",
            "data engineer", "data scientist", "data analytics", "analista de datos",
            "ciencia de datos", "soporte ti", "soporte técnico ti", "soporte computacional",
            "administrador de sistemas", "ingeniero de sistemas", "ingeniería de sistemas",
            "analista de sistemas", "sistemas informáticos", "arquitecto de software",
            "dba", "administrador de base de datos", "redes y telecomunicaciones"
        ]

        it_tech_stack = [
            "python", "javascript", "typescript", "react", "angular", "vue", "node", "nodejs",
            "django", "fastapi", "flask", "springboot", "spring boot", "laravel",
            "docker", "kubernetes", "aws", "azure", "gcp", "linux", "sql server",
            "postgresql", "mongodb", "mysql", "api rest", "microservicios", "git"
        ]

        is_it_job = False
        if not is_non_it_trade or has_strict_it_title:
            # Coincidencia directa en título con término de TI
            if any(re.search(r"\b" + re.escape(kw) + r"\b", title_lower) for kw in it_title_keywords):
                is_it_job = True
            # O presencia de tecnologías específicas en el texto si el título no es de otro rubro
            elif any(re.search(r"\b" + re.escape(st) + r"\b", text) for st in it_tech_stack):
                tech_title_hints = [
                    "ingeniero", "analista", "consultor", "especialista", "técnico", "tecnico", "lead", "developer"
                ]
                if any(re.search(r"\b" + re.escape(h) + r"\b", title_lower) for h in tech_title_hints):
                    is_it_job = True

        if is_it_job:
            # Comprobar ubicación: Debe ser entre Concepción y Ñuble, o Remoto/Híbrido/Chile nacional
            loc_combined = f"{job.region or ''} {job.comuna or ''} {job.location_raw or ''}".lower()
            excluded_distant_regions = [
                "antofagasta", "calama", "tarapacá", "iquique", "arica", "atacama",
                "copiapó", "coquimbo", "la serena", "magallanes", "punta arenas", "aysén", "coyhaique"
            ]
            if job.modality.value == "presencial" and any(dr in loc_combined for dr in excluded_distant_regions):
                return None
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
    ) -> bool:
        """Envía una notificación al canal de Discord correspondiente usando Discord Components V2.

        NUNCA envía a mensaje privado (DM), respetando la directiva explícita del usuario.
        Retorna True si se despachó el mensaje a Discord, False en caso contrario.
        """
        try:
            channel_id = self.get_destination_channel_id(job)
            if not channel_id:
                logger.debug(
                    "La vacante #%d no coincide con los canales de destino configurados.", job_id
                )
                return False

            target_channel = self.get_channel(channel_id) or await self.fetch_channel(channel_id)
            if not target_channel or not isinstance(
                target_channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)
            ):
                logger.warning(
                    "No se pudo acceder al canal de destino %s para la oferta #%d.",
                    channel_id,
                    job_id,
                )
                return False

            embed = create_job_card_embed(job, match_result=match_result, job_id=job_id)
            view = JobCardView(job_url=job.url, job_id=job_id)
            await target_channel.send(embed=embed, view=view)

            logger.info(
                "Notificación publicada en #%s (%s) para oferta #%d: %s",
                getattr(target_channel, "name", "canal"),
                channel_id,
                job_id,
                job.title,
            )
            return True
        except Exception as e:
            logger.error("Error al publicar notificación para oferta #%d: %s", job_id, e)
            return False

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
