"""Estructuras y validadores para formularios interactivos de postulación."""

from __future__ import annotations

from pydantic import BaseModel, Field

# Límites de Discord para componentes y modales
DISCORD_MODAL_TITLE_MAX = 45
DISCORD_TEXT_INPUT_LABEL_MAX = 45
DISCORD_TEXT_INPUT_VALUE_MAX = 4000
DISCORD_SELECT_OPTIONS_MAX = 25


class FormQuestion(BaseModel):
    """Representa una pregunta de postulación."""

    key: str
    question_text: str = Field(..., max_length=500)
    current_answer: str | None = Field(default=None, max_length=DISCORD_TEXT_INPUT_VALUE_MAX)
    is_required: bool = True
    is_verified: bool = False
    source: str = "manual"  # manual, profile, reusable


class ApplicationDraft(BaseModel):
    """Borrador completo de una postulación."""

    application_id: int
    job_id: int
    job_title: str
    company: str
    job_url: str
    recommended_resume_id: int | None = None
    recommended_resume_name: str | None = None
    questions: list[FormQuestion] = Field(default_factory=list)
    notes: str | None = None
    is_ready_for_review: bool = False

    @property
    def pending_questions_count(self) -> int:
        """Cantidad de preguntas obligatorias que aún no tienen respuesta válida."""
        count = 0
        for q in self.questions:
            if q.is_required and (not q.current_answer or q.current_answer.startswith("(")):
                count += 1
        return count
