"""Definición de comandos de aplicación Slash para EmpleoRadar (/empleo ...)."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from app.bot.embeds import (
    create_health_embed,
    create_job_card_embed,
    create_profile_embed,
)
from app.bot.modals.forms_modals import EditProfileBasicModal
from app.bot.views.job_views import JobCardView
from app.jobs.matching import evaluate_job_match
from app.profile.preferences import criteria_from_db_preferences
from app.security.permissions import owner_check

logger = logging.getLogger(__name__)


class EmpleoCog(
    commands.GroupCog,
    group_name="empleo",
    group_description="Comandos de búsqueda y postulación laboral",
):
    """Grupo principal de comandos slash /empleo."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        super().__init__()

    # Inyección de dependencias desde el bot
    @property
    def repo(self):
        return self.bot.repo  # type: ignore[attr-defined]

    @property
    def profile_service(self):
        return self.bot.profile_service  # type: ignore[attr-defined]

    @property
    def app_service(self):
        return self.bot.app_service  # type: ignore[attr-defined]

    @property
    def scheduler_runner(self):
        return self.bot.scheduler_runner  # type: ignore[attr-defined]

    @property
    def health_monitor(self):
        return self.bot.health_monitor  # type: ignore[attr-defined]

    @property
    def source_registry(self):
        return self.bot.source_registry  # type: ignore[attr-defined]

    # --- /empleo ayuda ---
    @app_commands.command(
        name="ayuda", description="Muestra el manual de uso y comandos disponibles."
    )
    @app_commands.check(owner_check)
    async def ayuda(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="📖 Manual de Comandos de EmpleoRadar",
            description="Bot personal para detección, filtrado y postulación a ofertas laborales en Ñuble y Chile.",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="🔍 Búsqueda y Ofertas",
            value=(
                "• `/empleo recientes [limite]` - Muestra las últimas ofertas detectadas.\n"
                "• `/empleo buscar <texto>` - Busca vacantes por palabras clave o cargo.\n"
                "• `/empleo ver <id>` - Muestra el detalle completo de una vacante por ID."
            ),
            inline=False,
        )
        embed.add_field(
            name="👤 Perfil y Currículum",
            value=(
                "• `/empleo perfil` - Ver y editar tu perfil profesional.\n"
                "• `/empleo cv` - Subir un nuevo archivo PDF de currículum o listar los actuales.\n"
                "• `/empleo preguntas` - Gestionar respuestas reutilizables a preguntas típicas."
            ),
            inline=False,
        )
        embed.add_field(
            name="📬 Postulaciones e Historial",
            value=(
                "• `/empleo postular <id>` - Inicia la preparación asistida para una vacante.\n"
                "• `/empleo postulaciones` - Ver postulaciones activas y borradores.\n"
                "• `/empleo historial` - Historial completo de ofertas postuladas."
            ),
            inline=False,
        )
        embed.add_field(
            name="⚙️ Configuración y Salud",
            value=(
                "• `/empleo fuentes` - Lista el estado operativo de los portales de empleo.\n"
                "• `/empleo estado` - Resumen rápido de actividad.\n"
                "• `/empleo salud` - Diagnóstico de base de datos, memoria y conexiones.\n"
                "• `/empleo pausa` / `/empleo reanudar` - Pausar o reactivar notificaciones."
            ),
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- /empleo estado ---
    @app_commands.command(
        name="estado", description="Muestra el estado actual del bot y notificaciones."
    )
    @app_commands.check(owner_check)
    async def estado(self, interaction: discord.Interaction) -> None:
        db_owner = await self.repo.get_or_create_owner(interaction.user.id)
        prefs = await self.repo.get_or_create_preferences(db_owner.id)
        stats = await self.repo.get_job_stats()
        app_stats = await self.repo.get_application_stats(db_owner.id)

        estado_notif = "⏸️ Pausadas" if prefs.is_paused else "▶️ Activas"
        embed = discord.Embed(
            title="📊 Estado de EmpleoRadar",
            color=discord.Color.green() if not prefs.is_paused else discord.Color.orange(),
        )
        embed.add_field(name="🔔 Notificaciones", value=estado_notif, inline=True)
        embed.add_field(name="📍 Región Foco", value="Ñuble (Chillán y comunas)", inline=True)
        embed.add_field(
            name="📈 Ofertas en BD", value=f"Total: {stats.get('total', 0)}", inline=True
        )

        app_summary = "\n".join(
            f"• {status.capitalize()}: {count}" for status, count in app_stats.items()
        )
        embed.add_field(
            name="📁 Postulaciones", value=app_summary or "Ninguna registrada aún.", inline=False
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- /empleo buscar ---
    @app_commands.command(
        name="buscar", description="Busca ofertas por cargo, empresa o tecnología."
    )
    @app_commands.describe(texto="Palabra clave o cargo a buscar (ej: Python, Soporte, Chillán)")
    @app_commands.check(owner_check)
    async def buscar(self, interaction: discord.Interaction, texto: str) -> None:
        await interaction.response.defer(ephemeral=True)
        jobs = await self.repo.search_jobs(texto, limit=5)
        if not jobs:
            await interaction.followup.send(
                f"🔍 No se encontraron ofertas con el término **{texto}**.", ephemeral=True
            )
            return

        db_owner = await self.repo.get_or_create_owner(interaction.user.id)
        prefs = await self.repo.get_or_create_preferences(db_owner.id)
        criteria = criteria_from_db_preferences(prefs)

        await interaction.followup.send(
            f"🔎 Resultados encontrados para: **{texto}** ({len(jobs)})", ephemeral=True
        )
        for job in jobs:
            from app.jobs.models import JobPayload

            payload = JobPayload(
                source_name=job.source.name if job.source else "Fuente",
                external_id=job.external_id,
                title=job.title,
                company=job.company,
                description=job.description,
                region=job.region,
                comuna=job.comuna,
                url=job.url,
            )
            match_res = evaluate_job_match(payload, criteria)
            embed = create_job_card_embed(job, match_result=match_res, job_id=job.id)
            view = JobCardView(
                job_id=job.id,
                job_url=job.url,
                owner_id=interaction.user.id,
                application_service=self.app_service,
                repository=self.repo,
            )
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    # --- /empleo recientes ---
    @app_commands.command(
        name="recientes", description="Muestra las ofertas más recientes detectadas."
    )
    @app_commands.describe(limite="Cantidad de ofertas a mostrar (máximo 10, por defecto 5)")
    @app_commands.check(owner_check)
    async def recientes(self, interaction: discord.Interaction, limite: int | None = 5) -> None:
        await interaction.response.defer(ephemeral=True)
        limite = min(max(1, limite or 5), 10)
        jobs = await self.repo.get_recent_jobs(limit=limite)
        if not jobs:
            await interaction.followup.send(
                "📭 No hay ofertas registradas en la base de datos.", ephemeral=True
            )
            return

        db_owner = await self.repo.get_or_create_owner(interaction.user.id)
        prefs = await self.repo.get_or_create_preferences(db_owner.id)
        criteria = criteria_from_db_preferences(prefs)

        await interaction.followup.send(
            f"🕒 Mostrando las **{len(jobs)}** ofertas más recientes:", ephemeral=True
        )
        for job in jobs:
            from app.jobs.models import JobPayload

            payload = JobPayload(
                source_name=job.source.name if job.source else "Fuente",
                external_id=job.external_id,
                title=job.title,
                company=job.company,
                description=job.description,
                region=job.region,
                comuna=job.comuna,
                url=job.url,
            )
            match_res = evaluate_job_match(payload, criteria)
            embed = create_job_card_embed(job, match_result=match_res, job_id=job.id)
            view = JobCardView(
                job_id=job.id,
                job_url=job.url,
                owner_id=interaction.user.id,
                application_service=self.app_service,
                repository=self.repo,
            )
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    # --- /empleo ver ---
    @app_commands.command(
        name="ver", description="Consulta los detalles de una oferta por su ID numérico."
    )
    @app_commands.describe(oferta_id="ID de la oferta")
    @app_commands.check(owner_check)
    async def ver(self, interaction: discord.Interaction, oferta_id: int) -> None:
        job = await self.repo.get_job(oferta_id)
        if not job:
            await interaction.response.send_message(
                f"❌ La oferta con ID #{oferta_id} no existe.", ephemeral=True
            )
            return

        db_owner = await self.repo.get_or_create_owner(interaction.user.id)
        prefs = await self.repo.get_or_create_preferences(db_owner.id)
        criteria = criteria_from_db_preferences(prefs)

        from app.jobs.models import JobPayload

        payload = JobPayload(
            source_name=job.source.name if job.source else "Fuente",
            title=job.title,
            company=job.company,
            description=job.description,
            region=job.region,
            comuna=job.comuna,
            url=job.url,
        )
        match_res = evaluate_job_match(payload, criteria)
        embed = create_job_card_embed(job, match_result=match_res, job_id=job.id)
        view = JobCardView(
            job_id=job.id,
            job_url=job.url,
            owner_id=interaction.user.id,
            application_service=self.app_service,
            repository=self.repo,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # --- /empleo fuentes ---
    @app_commands.command(
        name="fuentes", description="Lista el estado operativo de todas las fuentes de empleo."
    )
    @app_commands.check(owner_check)
    async def fuentes(self, interaction: discord.Interaction) -> None:
        sources = self.source_registry.list_sources()
        embed = discord.Embed(
            title="🌐 Estado de Fuentes de Empleo",
            description="Monitor de conectores e integraciones autorizadas.",
            color=discord.Color.blue(),
        )
        for s in sources:
            st = s.status.value
            icon = "🟢" if st == "operativa" else ("🟡" if st == "limitada" else "🔴")
            notes = getattr(s, "access_notes", None) or "Operación estándar."
            last_chk = (
                s.last_checked_at.strftime("%Y-%m-%d %H:%M")
                if s.last_checked_at
                else "Pendiente de primer ciclo"
            )
            embed.add_field(
                name=f"{icon} {s.name} ({s.source_type})",
                value=f"• Estado: `{st}`\n• Última consulta: {last_chk}\n• Notas: {notes}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- /empleo perfil ---
    @app_commands.command(
        name="perfil", description="Ver y editar el perfil profesional y académico."
    )
    @app_commands.check(owner_check)
    async def perfil(self, interaction: discord.Interaction) -> None:
        db_owner = await self.repo.get_or_create_owner(interaction.user.id, interaction.user.name)
        profile = await self.profile_service.get_profile(db_owner.id)
        resumes = await self.profile_service.list_resumes(db_owner.id)

        profile_data = {
            "education": profile.education,
            "availability": profile.availability,
            "salary_expectation_min": profile.salary_expectation_min,
            "excel_level": profile.excel_level,
            "drivers_license": profile.drivers_license,
            "own_transport": profile.own_transport,
        }

        embed = create_profile_embed(
            owner_name=interaction.user.display_name,
            profile_data=profile_data,
            resumes=list(resumes),
        )

        class EditProfileView(discord.ui.View):
            def __init__(self, service, owner_id):
                super().__init__(timeout=300)
                self.service = service
                self.owner_id = owner_id

            @discord.ui.button(label="✏️ Editar Antecedentes", style=discord.ButtonStyle.primary)
            async def edit_btn(self, inter: discord.Interaction, btn: discord.ui.Button):
                async def save_cb(modal_inter: discord.Interaction, new_data: dict):
                    await self.service.update_profile(self.owner_id, **new_data)
                    await modal_inter.response.send_message(
                        "✅ Perfil actualizado exitosamente.", ephemeral=True
                    )

                modal = EditProfileBasicModal(profile_data, save_cb)
                await inter.response.send_modal(modal)

        view = EditProfileView(self.profile_service, db_owner.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # --- /empleo cv ---
    @app_commands.command(name="cv", description="Gestiona tus archivos de currículum (PDF).")
    @app_commands.describe(
        archivo="Archivo PDF del currículum a cargar",
        etiqueta="Especialidad o versión (ej: Desarrollo, Soporte, General)",
        marcar_predeterminado="Si debe quedar como CV predeterminado para postulaciones",
    )
    @app_commands.check(owner_check)
    async def cv(
        self,
        interaction: discord.Interaction,
        archivo: discord.Attachment | None = None,
        etiqueta: str | None = "General",
        marcar_predeterminado: bool | None = True,
    ) -> None:
        db_owner = await self.repo.get_or_create_owner(interaction.user.id)

        if archivo is None:
            # Listar CVs existentes
            resumes = await self.profile_service.list_resumes(db_owner.id)
            if not resumes:
                await interaction.response.send_message(
                    "📂 No tienes currículums guardados. Adjunta un archivo en este comando para subir uno.",
                    ephemeral=True,
                )
                return

            embed = discord.Embed(
                title="📂 Tus Currículums Almacenados", color=discord.Color.blue()
            )
            for r in resumes:
                star = " ⭐ (Predeterminado)" if r.is_default else ""
                embed.add_field(
                    name=f"ID #{r.id} - {r.original_filename}{star}",
                    value=f"• Versión: {r.version} | Etiqueta: {r.label}\n• Tamaño: {r.file_size // 1024} KB\n• Subido: {r.uploaded_at.strftime('%Y-%m-%d')}",
                    inline=False,
                )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Subir nuevo CV
        await interaction.response.defer(ephemeral=True)
        if not archivo.filename.lower().endswith(".pdf"):
            await interaction.followup.send(
                "❌ Solo se admiten archivos en formato PDF.", ephemeral=True
            )
            return

        content = await archivo.read()
        try:
            resume = await self.profile_service.upload_resume(
                owner_id=db_owner.id,
                filename=archivo.filename,
                content=content,
                label=etiqueta,
                is_default=marcar_predeterminado or False,
            )
            msg = f"✅ Currículum **{archivo.filename}** cargado y verificado con éxito (ID #{resume.id})."
            if resume.extracted_text:
                msg += f"\n📄 Texto extraído para postulaciones: {len(resume.extracted_text)} caracteres."
            await interaction.followup.send(msg, ephemeral=True)
        except Exception as e:
            logger.exception("Error al subir CV: %s", e)
            await interaction.followup.send(f"❌ Error al procesar el archivo: {e}", ephemeral=True)

    # --- /empleo preguntas ---
    @app_commands.command(
        name="preguntas", description="Muestra y edita las respuestas a preguntas frecuentes."
    )
    @app_commands.check(owner_check)
    async def preguntas(self, interaction: discord.Interaction) -> None:
        db_owner = await self.repo.get_or_create_owner(interaction.user.id)
        await self.profile_service.initialize_default_questions(db_owner.id)
        answers = await self.profile_service.get_reusable_answers(db_owner.id)

        embed = discord.Embed(
            title="💬 Respuestas Reutilizables Guardadas",
            description="Estas respuestas se usan para rellenar automáticamente preguntas en las postulaciones.",
            color=discord.Color.blue(),
        )
        for ans in answers:
            icon = "⚠️" if ans.answer_text.startswith("(") else "✅"
            embed.add_field(
                name=f"{icon} {ans.question_text}",
                value=ans.answer_text[:300],
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- /empleo postular ---
    @app_commands.command(
        name="postular", description="Prepara una postulación para una vacante específica por ID."
    )
    @app_commands.describe(oferta_id="ID de la oferta")
    @app_commands.check(owner_check)
    async def postular(self, interaction: discord.Interaction, oferta_id: int) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            db_owner = await self.repo.get_or_create_owner(interaction.user.id)
            draft = await self.app_service.prepare_application(owner_id=db_owner.id, job_id=oferta_id)

            from app.bot.views.application_views import ApplicationDraftView

            view = ApplicationDraftView(
                draft=draft,
                owner_id=interaction.user.id,
                app_service=self.app_service,
                repo=self.repo,
            )
            embed = view.build_embed()
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(
                f"❌ No se pudo preparar la postulación: {e}", ephemeral=True
            )

    # --- /empleo postulaciones ---
    @app_commands.command(
        name="postulaciones", description="Lista postulaciones en curso y en borrador."
    )
    @app_commands.check(owner_check)
    async def postulaciones(self, interaction: discord.Interaction) -> None:
        db_owner = await self.repo.get_or_create_owner(interaction.user.id)
        apps = await self.app_service.get_history(owner_id=db_owner.id, limit=10)
        if not apps:
            await interaction.response.send_message(
                "📭 No tienes postulaciones registradas aún.", ephemeral=True
            )
            return

        embed = discord.Embed(title="📁 Postulaciones Registradas", color=discord.Color.blue())
        for a in apps:
            job = await self.repo.get_job(a.job_id)
            title = job.title if job else f"Oferta #{a.job_id}"
            embed.add_field(
                name=f"ID #{a.id} • {title[:50]}",
                value=f"• Estado: `{a.status}`\n• Actualizada: {a.updated_at.strftime('%Y-%m-%d %H:%M')}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- /empleo historial ---
    @app_commands.command(
        name="historial", description="Muestra el historial completo de ofertas postuladas."
    )
    @app_commands.check(owner_check)
    async def historial(self, interaction: discord.Interaction) -> None:
        db_owner = await self.repo.get_or_create_owner(interaction.user.id)
        apps = await self.app_service.get_history(
            owner_id=db_owner.id, status="enviada_confirmada", limit=10
        )
        if not apps:
            await interaction.response.send_message(
                "📭 No hay postulaciones completadas en el historial.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📜 Historial de Postulaciones Enviadas", color=discord.Color.green()
        )
        for a in apps:
            job = await self.repo.get_job(a.job_id)
            title = job.title if job else f"Oferta #{a.job_id}"
            company = job.company if job else "Confidencial"
            embed.add_field(
                name=f"{title} ({company})",
                value=f"• Enviada: {a.updated_at.strftime('%Y-%m-%d')}\n• Enlace: {job.url if job else 'N/A'}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- /empleo pausa ---
    @app_commands.command(
        name="pausa", description="Pausa temporalmente las notificaciones de nuevas ofertas."
    )
    @app_commands.check(owner_check)
    async def pausa(self, interaction: discord.Interaction) -> None:
        db_owner = await self.repo.get_or_create_owner(interaction.user.id)
        await self.repo.update_preferences(owner_id=db_owner.id, is_paused=True)
        await interaction.response.send_message(
            "⏸️ Las notificaciones de nuevas ofertas han sido **pausadas**.",
            ephemeral=True,
        )

    # --- /empleo reanudar ---
    @app_commands.command(
        name="reanudar", description="Reanuda las notificaciones de nuevas ofertas."
    )
    @app_commands.check(owner_check)
    async def reanudar(self, interaction: discord.Interaction) -> None:
        db_owner = await self.repo.get_or_create_owner(interaction.user.id)
        await self.repo.update_preferences(owner_id=db_owner.id, is_paused=False)
        await interaction.response.send_message(
            "▶️ Las notificaciones de nuevas ofertas han sido **reanudadas**.",
            ephemeral=True,
        )

    # --- /empleo salud ---
    @app_commands.command(
        name="salud", description="Diagnóstico técnico del sistema y estado de conectividad."
    )
    @app_commands.check(owner_check)
    async def salud(self, interaction: discord.Interaction) -> None:
        health_data = await self.health_monitor.get_system_health(
            discord_connected=self.bot.is_ready()
        )
        embed = create_health_embed(health_data)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- /empleo configurar ---
    @app_commands.command(
        name="configurar", description="Muestra o ajusta parámetros generales de búsqueda."
    )
    @app_commands.describe(
        sueldo_minimo="Sueldo líquido mínimo esperado en CLP (ej: 1000000)",
        excluir_practicas="Si se deben excluir prácticas profesionales (True/False)",
    )
    @app_commands.check(owner_check)
    async def configurar(
        self,
        interaction: discord.Interaction,
        sueldo_minimo: int | None = None,
        excluir_practicas: bool | None = None,
    ) -> None:
        db_owner = await self.repo.get_or_create_owner(interaction.user.id)
        update_args = {}
        if sueldo_minimo is not None:
            update_args["min_salary"] = sueldo_minimo
        if excluir_practicas is not None:
            update_args["exclude_internships"] = excluir_practicas

        if update_args:
            await self.repo.update_preferences(owner_id=db_owner.id, **update_args)
            await interaction.response.send_message(
                f"⚙️ Configuración actualizada: {update_args}",
                ephemeral=True,
            )
        else:
            prefs = await self.repo.get_or_create_preferences(db_owner.id)
            embed = discord.Embed(
                title="⚙️ Configuración de Filtros y Preferencias", color=discord.Color.blue()
            )
            embed.add_field(
                name="💰 Sueldo Mínimo",
                value=f"${prefs.min_salary:,} CLP" if prefs.min_salary else "Sin filtro",
                inline=True,
            )
            embed.add_field(
                name="🚫 Excluir Prácticas",
                value="Sí" if prefs.exclude_internships else "No",
                inline=True,
            )
            embed.add_field(
                name="🎯 Puntaje Mínimo Notificación",
                value=f"{prefs.min_score_notify}/100",
                inline=True,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
