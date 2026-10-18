"""Servicio central de postulaciones, borradores y seguimiento del estado."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from app.applications.answers import match_answer_for_question
from app.applications.forms import ApplicationDraft, FormQuestion
from app.applications.submission import ManualContinuationAdapter, SubmissionResult
from app.database.models import Application, ApplicationStatus, Resume
from app.database.repository import Repository
from app.profile.service import DEFAULT_QUESTION_KEYS, ProfileService

logger = logging.getLogger(__name__)


class ApplicationService:
    """Gestiona el ciclo de vida de postulaciones a ofertas de trabajo."""

    def __init__(
        self,
        repository: Repository,
        profile_service: ProfileService,
        require_confirmation: bool = True,
    ) -> None:
        self.repo = repository
        self.profile_service = profile_service
        self.require_confirmation = require_confirmation
        self.default_adapter = ManualContinuationAdapter()

    async def prepare_application(
        self,
        owner_id: int,
        job_id: int,
    ) -> ApplicationDraft:
        """Inicia o recupera el borrador de postulación para una vacante."""
        job = await self.repo.get_job(job_id)
        if not job:
            raise ValueError(f"La oferta #{job_id} no existe.")

        # Obtener o crear postulación
        app = await self.repo.get_application_for_job(owner_id=owner_id, job_id=job_id)
        if not app:
            app = await self.repo.create_application(owner_id=owner_id, job_id=job_id)
            await self.repo.update_application_status(
                application_id=app.id,
                status=ApplicationStatus.EN_PREPARACION.value,
                detail="Iniciada preparación de postulación.",
            )

        # Seleccionar CV predeterminado o el más adecuado
        default_resume = await self.repo.get_default_resume(owner_id=owner_id)
        if not default_resume:
            all_resumes = await self.repo.get_resumes(owner_id=owner_id)
            if all_resumes:
                default_resume = all_resumes[0]

        # Obtener respuestas del perfil y guardadas
        profile = await self.profile_service.get_profile(owner_id=owner_id)
        reusable_answers = await self.profile_service.get_reusable_answers(owner_id=owner_id)
        existing_answers = await self.repo.get_application_answers(application_id=app.id)
        existing_answers_map = {ans.question: ans.answer for ans in existing_answers}

        # Preparar preguntas requeridas
        form_questions: list[FormQuestion] = []
        for q_key, q_text in DEFAULT_QUESTION_KEYS:
            current_ans = existing_answers_map.get(q_text)
            source = "saved"
            is_verified = True
            if not current_ans:
                ans_text, source, is_verified = match_answer_for_question(
                    q_text, profile, list(reusable_answers)
                )
                current_ans = ans_text

            form_questions.append(
                FormQuestion(
                    key=q_key,
                    question_text=q_text,
                    current_answer=current_ans,
                    is_required=True,
                    is_verified=is_verified,
                    source=source,
                )
            )

        return ApplicationDraft(
            application_id=app.id,
            job_id=job.id,
            job_title=job.title,
            company=job.company or "Empresa Confidencial",
            job_url=job.url,
            recommended_resume_id=default_resume.id if default_resume else None,
            recommended_resume_name=default_resume.original_filename if default_resume else None,
            questions=form_questions,
            is_ready_for_review=all(not q.current_answer.startswith("(") for q in form_questions),
        )

    async def save_answer(
        self,
        application_id: int,
        question: str,
        answer: str,
    ) -> None:
        """Guarda o actualiza la respuesta para una pregunta específica."""
        await self.repo.save_application_answer(
            application_id=application_id,
            question=question,
            answer=answer,
            source="manual",
        )

    async def mark_as_applied(
        self,
        owner_id: int,
        job_id: int,
        notes: str | None = None,
    ) -> Application:
        """Marca directamente una oferta como ya postulada por el usuario."""
        app = await self.repo.get_application_for_job(owner_id=owner_id, job_id=job_id)
        if not app:
            app = await self.repo.create_application(owner_id=owner_id, job_id=job_id)

        await self.repo.update_application_status(
            application_id=app.id,
            status=ApplicationStatus.ENVIADA_CONFIRMADA.value,
            detail=notes or "Marcada manualmente como postulada por el usuario.",
        )
        return app

    async def submit_application(
        self,
        owner_id: int,
        application_id: int,
        confirmed_by_user: bool = False,
    ) -> SubmissionResult:
        """Ejecuta el envío de la postulación previo cumplimiento de confirmación obligatoria."""
        if self.require_confirmation and not confirmed_by_user:
            return SubmissionResult(
                success=False,
                status=ApplicationStatus.PENDIENTE_CONFIRMACION,
                message="Se requiere confirmación explícita del usuario antes de proceder al envío.",
            )

        app = await self.repo.get_application(application_id)
        if not app or app.owner_id != owner_id:
            raise ValueError("Postulación no encontrada o no autorizada.")

        job = await self.repo.get_job(app.job_id)
        if not job:
            raise ValueError("La oferta asociada no existe.")

        resume: Resume | None = None
        if app.resume_id:
            resumes = await self.repo.get_resumes(owner_id=owner_id)
            resume = next((r for r in resumes if r.id == app.resume_id), None)
        if not resume:
            resume = await self.repo.get_default_resume(owner_id=owner_id)

        # Recopilar respuestas finales
        raw_answers = await self.repo.get_application_answers(application_id=app.id)
        answers_dict = {ans.question: ans.answer for ans in raw_answers}

        # Delegar en el adaptador
        result = await self.default_adapter.submit(
            application=app,
            job=job,
            resume=resume,
            answers=answers_dict,
            repository=self.repo,
        )

        return result

    async def get_history(
        self,
        owner_id: int,
        status: str | None = None,
        limit: int = 20,
    ) -> Sequence[Application]:
        """Consulta el historial de postulaciones."""
        return await self.repo.get_applications(owner_id=owner_id, status=status, limit=limit)
