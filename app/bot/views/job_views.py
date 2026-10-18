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
