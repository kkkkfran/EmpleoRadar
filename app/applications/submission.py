"""Adaptadores de envío y finalización de postulaciones."""

from __future__ import annotations

import abc
import logging

from pydantic import BaseModel

from app.database.models import Application, ApplicationStatus, Job, Resume
from app.database.repository import Repository

logger = logging.getLogger(__name__)


class SubmissionResult(BaseModel):
    """Resultado del proceso de envío o preparación de postulación."""

    success: bool
    status: ApplicationStatus
    confirmation_id: str | None = None
    confirmation_detail: str | None = None
    message: str
    portal_url: str | None = None
    manual_instructions: str | None = None


class BaseSubmissionAdapter(abc.ABC):
    """Adaptador base para tramitar postulaciones según el portal."""

    @abc.abstractmethod
    async def can_handle(self, job: Job) -> bool:
        """Determina si este adaptador puede procesar la vacante."""
        pass

    @abc.abstractmethod
    async def submit(
        self,
        application: Application,
        job: Job,
        resume: Resume | None,
        answers: dict[str, str],
        repository: Repository,
    ) -> SubmissionResult:
        """Ejecuta o prepara el envío de la postulación."""
        pass


class ManualContinuationAdapter(BaseSubmissionAdapter):
    """Adaptador seguro por defecto para portales web sin API de envío directo.

    Abre el enlace oficial del portal, proporciona las respuestas listas para copiar
    y el currículum adecuado, garantizando el cumplimiento de los Términos de Servicio.
    """

    async def can_handle(self, job: Job) -> bool:
        return True  # Maneja cualquier portal por defecto de forma segura

    async def submit(
        self,
        application: Application,
        job: Job,
        resume: Resume | None,
        answers: dict[str, str],
        repository: Repository,
    ) -> SubmissionResult:
        """Prepara las respuestas para postulación asistida sin vulnerar controles antibot."""
        logger.info("Preparando postulación asistida para vacante #%d en %s", job.id, job.company)

        formatted_answers = []
        for q, a in answers.items():
            formatted_answers.append(f"• **{q}**\n  ↪ {a}")

        answers_text = (
            "\n\n".join(formatted_answers)
            if formatted_answers
            else "No se requieren preguntas adicionales."
        )
        resume_name = resume.original_filename if resume else "Ninguno seleccionado"

        instructions = (
            f"1. Abre el enlace oficial: {job.url}\n"
            f"2. Utiliza tu CV seleccionado: **{resume_name}**\n"
            f"3. Copia tus respuestas preparadas:\n\n{answers_text}"
        )

        # Actualizar estado a REQUIERE_INTERVENCION (para que el usuario complete en el portal)
        await repository.update_application_status(
            application_id=application.id,
            status=ApplicationStatus.REQUIERE_INTERVENCION.value,
            detail="Postulación preparada para completar en portal oficial.",
        )

        return SubmissionResult(
            success=True,
            status=ApplicationStatus.REQUIERE_INTERVENCION,
            message="Postulación preparada exitosamente. Completa el envío en el portal oficial.",
            portal_url=job.url,
            manual_instructions=instructions,
        )
