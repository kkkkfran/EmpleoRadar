"""Vistas interactivas para el borrador y confirmación de postulaciones."""

from __future__ import annotations

import logging

import discord
from discord import ui

from app.applications.forms import ApplicationDraft
from app.bot.modals.forms_modals import EditAnswerModal

logger = logging.getLogger(__name__)


class ApplicationDraftView(ui.View):
    """Vista de gestión del borrador de postulación y edición de respuestas."""

    def __init__(
        self,
        draft: ApplicationDraft,
        owner_id: int,
        app_service,
        repo,
        timeout: float | None = 1800,  # 30 minutos
    ) -> None:
        super().__init__(timeout=timeout)
        self.draft = draft
        self.owner_id = owner_id
        self.app_service = app_service
        self.repo = repo
        self._add_question_selector()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("⛔ Acceso denegado.", ephemeral=True)
            return False
        return True

    def _add_question_selector(self) -> None:
        """Crea el menú de selección de preguntas para responder o editar."""
        options = []
        for q in self.draft.questions[:25]:  # Límite de Discord
            status_icon = "⚠️" if q.current_answer.startswith("(") else "✅"
            options.append(
                discord.SelectOption(
                    label=f"{status_icon} {q.question_text[:95]}",
                    value=q.key,
                    description=q.current_answer[:95],
                )
            )

        if options:
            select = ui.Select(
                placeholder="Selecciona una pregunta para responder o editar...",
                options=options,
                custom_id="select_question",
                row=0,
            )
            select.callback = self._on_question_selected
            self.add_item(select)

    async def _on_question_selected(self, interaction: discord.Interaction) -> None:
        selected_key = interaction.data["values"][0]  # type: ignore[index]
        target_q = next((q for q in self.draft.questions if q.key == selected_key), None)
        if not target_q:
            await interaction.response.send_message("Pregunta no encontrada.", ephemeral=True)
            return

        async def save_callback(inter: discord.Interaction, q_text: str, new_ans: str) -> None:
            await self.app_service.save_answer(
                application_id=self.draft.application_id,
                question=q_text,
                answer=new_ans,
            )
            target_q.current_answer = new_ans
            target_q.is_verified = True

            # Refrescar vista
            embed = self.build_embed()
            await inter.response.edit_message(embed=embed, view=self)

        modal = EditAnswerModal(
            question_text=target_q.question_text,
            current_answer=target_q.current_answer or "",
            on_save_callback=save_callback,
        )
        await interaction.response.send_modal(modal)

    def build_embed(self) -> discord.Embed:
        """Construye el Embed de resumen del borrador."""
        embed = discord.Embed(
            title=f"📋 Preparando Postulación: {self.draft.job_title}",
            description=f"**Empresa:** {self.draft.company}\n**Enlace:** [Ver oferta original]({self.draft.job_url})",
            color=discord.Color.blue(),
        )

        cv_text = self.draft.recommended_resume_name or "Ningún CV cargado"
        embed.add_field(name="📄 Currículum Asignado", value=f"• **{cv_text}**", inline=False)

        q_lines = []
        for i, q in enumerate(self.draft.questions, 1):
            icon = "⚠️" if q.current_answer.startswith("(") else "✅"
            q_lines.append(f"{icon} **{i}. {q.question_text}**\n↪ {q.current_answer}")

        embed.add_field(
            name=f"📝 Respuestas ({len(self.draft.questions)})",
            value="\n\n".join(q_lines) if q_lines else "No se requieren preguntas.",
            inline=False,
        )

        if self.draft.pending_questions_count > 0:
            embed.set_footer(
                text=f"⚠️ Faltan {self.draft.pending_questions_count} respuestas requeridas antes de enviar."
            )
        else:
            embed.set_footer(
                text="✅ Todas las respuestas completadas. Listo para revisar y enviar."
            )

        return embed

    @ui.button(label="🚀 Tramitar postulación", style=discord.ButtonStyle.success, row=1)
    async def submit_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Paso de confirmación previa obligatoria antes de tramitar."""
        confirm_view = ConfirmSubmitView(
            draft=self.draft,
            owner_id=self.owner_id,
            app_service=self.app_service,
        )
        msg = (
            "⚠️ **Confirmación de Envío Requerida**\n"
            "¿Deseas tramitar esta postulación con las respuestas y el currículum preparados?\n"
            "EmpleoRadar respetará los términos del portal y te proporcionará las instrucciones finales."
        )
        await interaction.response.send_message(msg, view=confirm_view, ephemeral=True)


class ConfirmSubmitView(ui.View):
    """Vista modal de confirmación estricta de envío."""

    def __init__(self, draft: ApplicationDraft, owner_id: int, app_service) -> None:
        super().__init__(timeout=300)
        self.draft = draft
        self.owner_id = owner_id
        self.app_service = app_service

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    @ui.button(label="✅ Sí, confirmar tramitación", style=discord.ButtonStyle.success)
    async def confirm_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            db_owner = await self.app_service.repo.get_or_create_owner(interaction.user.id)
            result = await self.app_service.submit_application(
                owner_id=db_owner.id,
                application_id=self.draft.application_id,
                confirmed_by_user=True,
            )

            res_embed = discord.Embed(
                title="📬 Postulación Tramitada",
                description=result.message,
                color=discord.Color.green(),
            )
            if result.manual_instructions:
                res_embed.add_field(
                    name="📌 Instrucciones y Respuestas para el Portal",
                    value=result.manual_instructions[:1000],
                    inline=False,
                )
            if result.portal_url:
                res_embed.add_field(name="🔗 Portal Oficial", value=result.portal_url, inline=False)

            self.stop()
            await interaction.followup.send(embed=res_embed, ephemeral=True)
        except Exception as e:
            logger.exception("Error al confirmar postulación: %s", e)
            await interaction.followup.send(f"❌ Error al tramitar: {e}", ephemeral=True)

    @ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.stop()
        await interaction.response.send_message(
            "Operación cancelada. El borrador sigue guardado.", ephemeral=True
        )
