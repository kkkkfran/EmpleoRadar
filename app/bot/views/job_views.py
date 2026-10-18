"""Vistas interactivas y botones para tarjetas de ofertas de empleo."""

from __future__ import annotations

import logging

import discord
from discord import ui

logger = logging.getLogger(__name__)


class JobCardView(ui.View):
    """Botonera interactiva para la tarjeta de una oferta laboral."""

    def __init__(
        self,
        job_id: int,
        job_url: str,
        owner_id: int,
        application_service,
        repository,
        timeout: float | None = 86400,  # 24 horas activa
    ) -> None:
        super().__init__(timeout=timeout)
        self.job_id = job_id
        self.job_url = job_url
        self.owner_id = owner_id
        self.app_service = application_service
        self.repo = repository

        # Botón de enlace directo a la oferta
        if job_url and (job_url.startswith("http://") or job_url.startswith("https://")):
            self.add_item(ui.Button(label="🔗 Ver oferta", url=job_url, row=0))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Verifica que solo el propietario autorizado pueda interactuar con los botones."""
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "⛔ Solo el propietario de EmpleoRadar puede gestionar estas ofertas.",
                ephemeral=True,
            )
            return False
        return True

    @ui.button(label="📝 Preparar postulación", style=discord.ButtonStyle.primary, row=0)
    async def prepare_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Inicia el borrador y abre el flujo de postulación."""
        await interaction.response.defer(ephemeral=True)
        try:
            db_owner = await self.repo.get_or_create_owner(interaction.user.id)
            draft = await self.app_service.prepare_application(
                owner_id=db_owner.id,
                job_id=self.job_id,
            )

            # Generar vista previa del borrador
            from app.bot.views.application_views import ApplicationDraftView

            view = ApplicationDraftView(
                draft=draft,
                owner_id=self.owner_id,
                app_service=self.app_service,
                repo=self.repo,
            )
            embed = view.build_embed()
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            logger.exception("Error al preparar postulación: %s", e)
            await interaction.followup.send(
                f"❌ Error al preparar la postulación: {e}", ephemeral=True
            )

    @ui.button(label="💾 Guardar oferta", style=discord.ButtonStyle.secondary, row=1)
    async def save_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Guarda la oferta en la lista de favoritos."""
        try:
            db_owner = await self.repo.get_or_create_owner(interaction.user.id)
            await self.repo.save_job(owner_id=db_owner.id, job_id=self.job_id)
            await interaction.response.send_message(
                "✅ Oferta guardada en tus favoritos.", ephemeral=True
            )
            button.disabled = True
            button.label = "💾 Guardada"
            await interaction.message.edit(view=self)
        except ValueError:
            await interaction.response.send_message(
                "ℹ️ Esta oferta ya está guardada.", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error al guardar oferta: {e}", ephemeral=True
            )

    @ui.button(label="✅ Marcar postulada", style=discord.ButtonStyle.success, row=1)
    async def mark_applied_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Marca la vacante como ya postulada externamente."""
        try:
            db_owner = await self.repo.get_or_create_owner(interaction.user.id)
            await self.app_service.mark_as_applied(
                owner_id=db_owner.id,
                job_id=self.job_id,
                notes="Marcada como postulada desde la tarjeta de Discord.",
            )
            await interaction.response.send_message(
                "🎉 ¡Excelente! La vacante fue registrada como **Postulada** en tu historial.",
                ephemeral=True,
            )
            button.disabled = True
            button.label = "✅ Postulada"
            await interaction.message.edit(view=self)
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error al registrar postulación: {e}", ephemeral=True
            )

    @ui.button(label="🗑️ Descartar", style=discord.ButtonStyle.danger, row=1)
    async def dismiss_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Oculta o descarta la notificación."""
        try:
            await interaction.message.delete()
        except discord.NotFound:
            pass
        except Exception:
            await interaction.response.send_message("Oferta descartada.", ephemeral=True)


class JobCardLayoutView(ui.LayoutView):
    """Tarjeta moderna para ofertas de empleo usando Discord Components V2 (LayoutView y Separator)."""

    def __init__(
        self,
        job,
        match_result,
        job_id: int,
        owner_id: int,
        application_service,
        repository,
        timeout: float | None = 86400,
    ) -> None:
        super().__init__(timeout=timeout)
        self.job = job
        self.match_result = match_result
        self.job_id = job_id
        self.owner_id = owner_id
        self.app_service = application_service
        self.repo = repository

        # 1. Cabecera principal: Título, Empresa, Ubicación y Condiciones
        company_str = job.company or "Confidencial / Empresa destacada"
        loc_str = job.comuna or job.region or job.location_raw or "Chile"
        if job.region and job.comuna and job.region != job.comuna:
            loc_str = f"{job.comuna}, {job.region}"

        header_lines = [
            f"### 💼 {job.title}",
            f"🏢 **Empresa:** {company_str} • 📍 **Ubicación:** {loc_str}",
            f"⚙️ **Modalidad:** {job.modality.value.capitalize()} • 📄 **Contrato:** {job.contract_type.value.capitalize()} • ⏰ **Jornada:** {job.schedule.value.capitalize()}",
        ]
        self.add_item(ui.TextDisplay("\n".join(header_lines)))

        # Separador V2 (Línea divisoria estética)
        self.add_item(ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small))

        # 2. Detalles de remuneración, experiencia y requisitos
        details_lines = []
        if job.salary_min or job.salary_max:
            if job.salary_min and job.salary_max:
                sal = f"${job.salary_min:,.0f} - ${job.salary_max:,.0f}".replace(",", ".")
            elif job.salary_min:
                sal = f"Desde ${job.salary_min:,.0f}".replace(",", ".")
            else:
                sal = f"Hasta ${job.salary_max:,.0f}".replace(",", ".")
            sal_type = f" ({job.salary_type})" if job.salary_type else ""
            details_lines.append(f"💰 **Remuneración:** {sal}{sal_type}")

        if job.experience_required:
            details_lines.append(f"⏳ **Experiencia requerida:** {job.experience_required}")
        if job.education_required:
            details_lines.append(f"🎓 **Nivel educacional:** {job.education_required}")

        # Compatibilidad con perfil
        score_emoji = "🎯" if match_result.score >= 50 else "⚡"
        details_lines.append(f"{score_emoji} **Compatibilidad:** `{match_result.score}/100`")
        reasons = getattr(match_result, "match_reasons", []) or getattr(match_result, "reasons", [])
        if reasons:
            details_lines.append(f"💡 *{reasons[0]}*")

        # Breve extracto de descripción si está disponible
        if job.description:
            clean_desc = " ".join(job.description.split())
            if len(clean_desc) > 220:
                clean_desc = clean_desc[:217] + "..."
            details_lines.append(f"📝 {clean_desc}")

        self.add_item(ui.TextDisplay("\n".join(details_lines)))

        # Separador V2
        self.add_item(ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small))

        # 3. Metadatos de origen y pie
        pub_str = (
            job.published_at.strftime("%d-%m-%Y %H:%M")
            if job.published_at
            else "Reciente"
        )
        footer_text = f"-# 🌐 Fuente: {job.source_name} | ID #{job_id} • Publicado: {pub_str} • EmpleoRadar"
        self.add_item(ui.TextDisplay(footer_text))

        # 4. Botones interactivos
        self.prepare_button = ui.Button(
            label="Preparar postulación",
            style=discord.ButtonStyle.primary,
            emoji="📝",
        )
        self.prepare_button.callback = self.on_prepare

        self.save_button = ui.Button(
            label="Guardar oferta",
            style=discord.ButtonStyle.secondary,
            emoji="💾",
        )
        self.save_button.callback = self.on_save

        self.mark_button = ui.Button(
            label="Marcar postulada",
            style=discord.ButtonStyle.success,
            emoji="✅",
        )
        self.mark_button.callback = self.on_mark_applied

        self.dismiss_button = ui.Button(
            label="Descartar",
            style=discord.ButtonStyle.danger,
            emoji="🗑️",
        )
        self.dismiss_button.callback = self.on_dismiss

        # Fila 1: Enlace directo y Preparar
        row1_items = []
        if job.url and (job.url.startswith("http://") or job.url.startswith("https://")):
            row1_items.append(
                ui.Button(
                    label="Ver oferta",
                    style=discord.ButtonStyle.link,
                    url=job.url,
                    emoji="🔗",
                )
            )
        row1_items.append(self.prepare_button)
        self.add_item(ui.ActionRow(*row1_items))

        # Fila 2: Guardar, Marcar postulada, Descartar
        self.add_item(ui.ActionRow(self.save_button, self.mark_button, self.dismiss_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Verifica que solo el propietario autorizado pueda interactuar con los botones."""
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "⛔ Solo el propietario de EmpleoRadar puede gestionar estas ofertas.",
                ephemeral=True,
            )
            return False
        return True

    async def on_prepare(self, interaction: discord.Interaction) -> None:
        """Inicia el borrador y abre el flujo de postulación."""
        await interaction.response.defer(ephemeral=True)
        try:
            db_owner = await self.repo.get_or_create_owner(interaction.user.id)
            draft = await self.app_service.prepare_application(
                owner_id=db_owner.id,
                job_id=self.job_id,
            )
            from app.bot.views.application_views import ApplicationDraftView

            view = ApplicationDraftView(
                draft=draft,
                owner_id=self.owner_id,
                app_service=self.app_service,
                repo=self.repo,
            )
            embed = view.build_embed()
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            logger.exception("Error al preparar postulación: %s", e)
            await interaction.followup.send(
                f"❌ Error al preparar la postulación: {e}", ephemeral=True
            )

    async def on_save(self, interaction: discord.Interaction) -> None:
        """Guarda la oferta en la lista de favoritos."""
        try:
            db_owner = await self.repo.get_or_create_owner(interaction.user.id)
            await self.repo.save_job(owner_id=db_owner.id, job_id=self.job_id)
            await interaction.response.send_message(
                "✅ Oferta guardada en tus favoritos.", ephemeral=True
            )
            self.save_button.disabled = True
            self.save_button.label = "Guardada"
            await interaction.message.edit(view=self)
        except ValueError:
            await interaction.response.send_message(
                "ℹ️ Esta oferta ya está guardada.", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error al guardar oferta: {e}", ephemeral=True
            )

    async def on_mark_applied(self, interaction: discord.Interaction) -> None:
        """Marca la vacante como ya postulada externamente."""
        try:
            db_owner = await self.repo.get_or_create_owner(interaction.user.id)
            await self.app_service.mark_as_applied(
                owner_id=db_owner.id,
                job_id=self.job_id,
                notes="Marcada como postulada desde la tarjeta de Discord.",
            )
            await interaction.response.send_message(
                "🎉 ¡Excelente! La vacante fue registrada como **Postulada** en tu historial.",
                ephemeral=True,
            )
            self.mark_button.disabled = True
            self.mark_button.label = "Postulada"
            await interaction.message.edit(view=self)
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error al registrar postulación: {e}", ephemeral=True
            )

    async def on_dismiss(self, interaction: discord.Interaction) -> None:
        """Oculta o descarta la notificación."""
        try:
            await interaction.message.delete()
        except discord.NotFound:
            pass
        except Exception:
            await interaction.response.send_message("Oferta descartada.", ephemeral=True)
