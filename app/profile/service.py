"""Servicio de gestión del perfil profesional, CVs y respuestas reutilizables."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from app.database.models import (
    CandidatePreferences,
    CandidateProfile,
    Owner,
    Resume,
    ReusableAnswer,
)
from app.database.repository import Repository
from app.profile.cv_storage import CVStorage

logger = logging.getLogger(__name__)

# Preguntas estándar frecuentes en portales de empleo de Chile
DEFAULT_QUESTION_KEYS = [
    ("exp_cargo", "¿Comente brevemente su experiencia en relación a este cargo?"),
    ("formacion", "¿Indique su nivel de estudios y carrera cursada?"),
    ("renta", "¿Cuáles son sus pretensiones de renta líquida mensual?"),
    ("disponibilidad", "¿Cuál es su disponibilidad para comenzar a trabajar?"),
    ("licencia_b", "¿Posee licencia de conducir clase B al día?"),
    ("movilizacion", "¿Cuenta con vehículo o movilización propia?"),
    ("excel", "¿Cuál es su nivel de manejo en Microsoft Excel?"),
    ("motivacion", "¿Qué le motiva a postular a esta posición y empresa?"),
]


class ProfileService:
    """Gestiona la información del candidato, almacenamiento de CV y respuestas preparadas."""

    def __init__(self, repository: Repository, cv_storage: CVStorage) -> None:
        self.repo = repository
        self.cv_storage = cv_storage

    async def get_or_create_owner(self, discord_id: int, username: str | None = None) -> Owner:
        """Obtiene o crea el propietario del bot."""
        return await self.repo.get_or_create_owner(discord_id=discord_id, username=username)

    async def get_profile(self, owner_id: int) -> CandidateProfile:
        """Obtiene el perfil del candidato asociado al propietario."""
        return await self.repo.get_or_create_profile(owner_id=owner_id)

    async def update_profile(self, owner_id: int, **kwargs) -> CandidateProfile:
        """Actualiza campos específicos del perfil."""
        return await self.repo.update_profile(owner_id=owner_id, **kwargs)

    async def get_preferences(self, owner_id: int) -> CandidatePreferences:
        """Obtiene las preferencias de búsqueda del candidato."""
        return await self.repo.get_or_create_preferences(owner_id=owner_id)

    async def update_preferences(self, owner_id: int, **kwargs) -> CandidatePreferences:
        """Actualiza preferencias de búsqueda."""
        return await self.repo.update_preferences(owner_id=owner_id, **kwargs)

    # --- Gestión de Currículum ---

    async def upload_resume(
        self,
        owner_id: int,
        filename: str,
        content: bytes,
        label: str | None = None,
        is_default: bool = False,
    ) -> Resume:
        """Valida, almacena en disco y registra en base de datos un nuevo CV."""
        stored_filename, file_hash, file_size, extracted_text = self.cv_storage.save_cv(
            owner_id=owner_id,
            filename=filename,
            content=content,
        )

        resume = await self.repo.add_resume(
            owner_id=owner_id,
            filename=stored_filename,
            original_filename=filename,
            file_hash=file_hash,
            file_size=file_size,
            mime_type="application/pdf",
            label=label or "General",
            extracted_text=extracted_text,
        )

        if is_default:
            await self.repo.set_default_resume(owner_id=owner_id, resume_id=resume.id)

        return resume

    async def list_resumes(self, owner_id: int) -> Sequence[Resume]:
        """Lista todos los CVs cargados por el propietario."""
        return await self.repo.get_resumes(owner_id=owner_id)

    async def delete_resume(self, owner_id: int, resume_id: int) -> bool:
        """Elimina un CV de la base de datos y del disco."""
        resumes = await self.repo.get_resumes(owner_id=owner_id)
        target = next((r for r in resumes if r.id == resume_id), None)
        if not target:
            return False

        # Eliminar archivo físico
        self.cv_storage.delete_cv(target.filename)
        # Eliminar registro en BD
        return await self.repo.delete_resume(resume_id=resume_id, owner_id=owner_id)

    async def set_default_resume(self, owner_id: int, resume_id: int) -> None:
        """Establece un CV como predeterminado para las postulaciones."""
        await self.repo.set_default_resume(owner_id=owner_id, resume_id=resume_id)

    # --- Respuestas Reutilizables ---

    async def get_reusable_answers(self, owner_id: int) -> Sequence[ReusableAnswer]:
        """Obtiene todas las respuestas guardadas del usuario."""
        profile = await self.get_profile(owner_id=owner_id)
        return await self.repo.get_reusable_answers(profile_id=profile.id)

    async def save_reusable_answer(
        self,
        owner_id: int,
        question_key: str,
        question_text: str,
        answer_text: str,
    ) -> ReusableAnswer:
        """Guarda o actualiza una respuesta reutilizable verificada."""
        profile = await self.get_profile(owner_id=owner_id)
        return await self.repo.save_reusable_answer(
            profile_id=profile.id,
            question_key=question_key,
            question_text=question_text,
            answer_text=answer_text.strip(),
        )

    async def initialize_default_questions(self, owner_id: int) -> None:
        """Inicializa las preguntas frecuentes estándar si no existen aún."""
        existing = await self.get_reusable_answers(owner_id)
        existing_keys = {ans.question_key for ans in existing}

        for q_key, q_text in DEFAULT_QUESTION_KEYS:
            if q_key not in existing_keys:
                await self.save_reusable_answer(
                    owner_id=owner_id,
                    question_key=q_key,
                    question_text=q_text,
                    answer_text="(Pendiente de completar por el usuario)",
                )
