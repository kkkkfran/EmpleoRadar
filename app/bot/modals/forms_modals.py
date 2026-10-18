"""Modales interactivos de Discord para responder preguntas y editar perfil."""

from __future__ import annotations

import contextlib

import discord
from discord import ui


class EditAnswerModal(ui.Modal):
    """Modal interactivo para responder o editar una pregunta de postulación."""

    def __init__(
        self,
        question_text: str,
        current_answer: str,
        on_save_callback,
    ) -> None:
        super().__init__(title="Responder Pregunta"[:45])
        self.question_text = question_text
        self.on_save_callback = on_save_callback

        self.answer_input = ui.TextInput(
            label=question_text[:45],
            style=discord.TextStyle.paragraph,
            placeholder="Escribe tu respuesta aquí...",
            default=current_answer if not current_answer.startswith("(") else "",
            required=True,
            max_length=2000,
        )
        self.add_item(self.answer_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.on_save_callback(
            interaction, self.question_text, self.answer_input.value.strip()
        )


class EditProfileBasicModal(ui.Modal, title="Editar Perfil Laboral"):
    """Modal para editar datos clave del perfil profesional."""

    def __init__(self, current_data: dict, on_save_callback) -> None:
        super().__init__()
        self.on_save_callback = on_save_callback

        self.education = ui.TextInput(
            label="Formación Académica",
            placeholder="Ej: Ingeniería en Informática, Titulado, Univ. del Bío-Bío",
            default=current_data.get("education") or "",
            required=True,
            max_length=200,
        )
        self.availability = ui.TextInput(
            label="Disponibilidad",
            placeholder="Ej: Inmediata / 2 semanas",
            default=current_data.get("availability") or "Inmediata",
            required=True,
            max_length=100,
        )
        self.salary = ui.TextInput(
            label="Pretensiones de Renta (Líquido CLP)",
            placeholder="Ej: 1200000",
            default=str(current_data.get("salary_expectation_min") or ""),
            required=False,
            max_length=15,
        )
        self.excel = ui.TextInput(
            label="Nivel de Excel",
            placeholder="Ej: Intermedio (Tablas dinámicas, BuscarV)",
            default=current_data.get("excel_level") or "Intermedio",
            required=False,
            max_length=100,
        )

        self.add_item(self.education)
        self.add_item(self.availability)
        self.add_item(self.salary)
        self.add_item(self.excel)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        sal_val = None
        if self.salary.value.strip():
            with contextlib.suppress(ValueError):
                sal_val = int(self.salary.value.strip().replace(".", "").replace("$", ""))

        data = {
            "education": self.education.value.strip(),
            "availability": self.availability.value.strip(),
            "salary_expectation_min": sal_val,
            "excel_level": self.excel.value.strip(),
        }
        await self.on_save_callback(interaction, data)
