"""Repositorio de acceso a datos para EmpleoRadar."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import (
    Application,
    ApplicationAnswer,
    ApplicationEvent,
    Base,
    CandidatePreferences,
    CandidateProfile,
    Job,
    JobObservation,
    JobSource,
    Notification,
    Owner,
    Resume,
    ReusableAnswer,
    SavedJob,
    SchemaMigration,
    SourceHealth,
)

logger = logging.getLogger(__name__)


class Database:
    """Gestor de conexión a la base de datos."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._engine = create_async_engine(
            url,
            echo=False,
            pool_pre_ping=True,
        )
        self._session_factory = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
        )

    async def create_tables(self) -> None:
        """Crea todas las tablas si no existen."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Tablas de base de datos creadas/verificadas")

    async def close(self) -> None:
        """Cierra la conexión a la base de datos."""
        await self._engine.dispose()
        logger.info("Conexión a base de datos cerrada")

    def session(self) -> AsyncSession:
        """Crea una nueva sesión."""
        return self._session_factory()


class Repository:
    """Repositorio con operaciones CRUD para todas las entidades."""

    def __init__(self, db: Database) -> None:
        self._db = db

    # --- Owner ---

    async def get_or_create_owner(self, discord_id: int, username: str | None = None) -> Owner:
        """Obtiene o crea el propietario por su ID de Discord."""
        async with self._db.session() as session:
            result = await session.execute(select(Owner).where(Owner.discord_id == discord_id))
            owner = result.scalar_one_or_none()
            if owner is None:
                owner = Owner(discord_id=discord_id, username=username)
                session.add(owner)
                await session.commit()
                await session.refresh(owner)
                logger.info("Propietario creado: discord_id=%s", discord_id)
            return owner

    async def get_owner(self, discord_id: int) -> Owner | None:
        """Obtiene el propietario por ID de Discord."""
        async with self._db.session() as session:
            result = await session.execute(select(Owner).where(Owner.discord_id == discord_id))
            return result.scalar_one_or_none()

    # --- Profile ---

    async def get_or_create_profile(self, owner_id: int) -> CandidateProfile:
        """Obtiene o crea el perfil del candidato."""
        async with self._db.session() as session:
            result = await session.execute(
                select(CandidateProfile).where(CandidateProfile.owner_id == owner_id)
            )
            profile = result.scalar_one_or_none()
            if profile is None:
                profile = CandidateProfile(owner_id=owner_id)
                session.add(profile)
                await session.commit()
                await session.refresh(profile)
            return profile

    async def update_profile(self, owner_id: int, **kwargs) -> CandidateProfile:
        """Actualiza campos del perfil del candidato."""
        async with self._db.session() as session:
            result = await session.execute(
                select(CandidateProfile).where(CandidateProfile.owner_id == owner_id)
            )
            profile = result.scalar_one_or_none()
            if profile is None:
                profile = CandidateProfile(owner_id=owner_id, **kwargs)
                session.add(profile)
            else:
                for key, value in kwargs.items():
                    if hasattr(profile, key):
                        setattr(profile, key, value)
            await session.commit()
            await session.refresh(profile)
            return profile

    # --- Preferences ---

    async def get_or_create_preferences(self, owner_id: int) -> CandidatePreferences:
        """Obtiene o crea las preferencias del candidato."""
        async with self._db.session() as session:
            result = await session.execute(
                select(CandidatePreferences).where(CandidatePreferences.owner_id == owner_id)
            )
            prefs = result.scalar_one_or_none()
            if prefs is None:
                prefs = CandidatePreferences(owner_id=owner_id)
                session.add(prefs)
                await session.commit()
                await session.refresh(prefs)
            return prefs

    async def update_preferences(self, owner_id: int, **kwargs) -> CandidatePreferences:
        """Actualiza preferencias del candidato."""
        async with self._db.session() as session:
            result = await session.execute(
                select(CandidatePreferences).where(CandidatePreferences.owner_id == owner_id)
            )
            prefs = result.scalar_one_or_none()
            if prefs is None:
                prefs = CandidatePreferences(owner_id=owner_id, **kwargs)
                session.add(prefs)
            else:
                for key, value in kwargs.items():
                    if hasattr(prefs, key):
                        setattr(prefs, key, value)
            await session.commit()
            await session.refresh(prefs)
            return prefs

    # --- Resumes ---

    async def add_resume(
        self,
        owner_id: int,
        filename: str,
        original_filename: str,
        file_hash: str,
        file_size: int,
        mime_type: str,
        label: str | None = None,
        extracted_text: str | None = None,
    ) -> Resume:
        """Agrega un nuevo CV."""
        async with self._db.session() as session:
            # Check for duplicate hash
            existing = await session.execute(
                select(Resume).where(
                    and_(Resume.owner_id == owner_id, Resume.file_hash == file_hash)
                )
            )
            if existing.scalar_one_or_none():
                raise ValueError("Ya existe un CV con el mismo contenido")

            # Get next version for this label
            version = 1
            if label:
                result = await session.execute(
                    select(func.max(Resume.version)).where(
                        and_(Resume.owner_id == owner_id, Resume.label == label)
                    )
                )
                max_ver = result.scalar()
                if max_ver:
                    version = max_ver + 1

            resume = Resume(
                owner_id=owner_id,
                filename=filename,
                original_filename=original_filename,
                file_hash=file_hash,
                file_size=file_size,
                mime_type=mime_type,
                label=label,
                extracted_text=extracted_text,
                version=version,
            )
            session.add(resume)
            await session.commit()
            await session.refresh(resume)
            return resume

    async def get_resumes(self, owner_id: int) -> Sequence[Resume]:
        """Lista los CVs del propietario."""
        async with self._db.session() as session:
            result = await session.execute(
                select(Resume)
                .where(Resume.owner_id == owner_id)
                .order_by(Resume.uploaded_at.desc())
            )
            return result.scalars().all()

    async def get_default_resume(self, owner_id: int) -> Resume | None:
        """Obtiene el CV marcado como default."""
        async with self._db.session() as session:
            result = await session.execute(
                select(Resume).where(
                    and_(Resume.owner_id == owner_id, Resume.is_default == True)  # noqa: E712
                )
            )
            return result.scalar_one_or_none()

    async def set_default_resume(self, owner_id: int, resume_id: int) -> None:
        """Establece un CV como predeterminado."""
        async with self._db.session() as session:
            # Unset all defaults
            await session.execute(
                update(Resume).where(Resume.owner_id == owner_id).values(is_default=False)
            )
            # Set new default
            await session.execute(
                update(Resume)
                .where(and_(Resume.id == resume_id, Resume.owner_id == owner_id))
                .values(is_default=True)
            )
            await session.commit()

    async def delete_resume(self, resume_id: int, owner_id: int) -> bool:
        """Elimina un CV."""
        async with self._db.session() as session:
            result = await session.execute(
                delete(Resume).where(and_(Resume.id == resume_id, Resume.owner_id == owner_id))
            )
            await session.commit()
            return result.rowcount > 0  # type: ignore[union-attr]

    # --- Job Sources ---

    async def get_or_create_source(self, name: str, **kwargs) -> JobSource:
        """Obtiene o crea una fuente de empleo."""
        kwargs.setdefault("source_type", "rss")
        async with self._db.session() as session:
            result = await session.execute(select(JobSource).where(JobSource.name == name))
            source = result.scalar_one_or_none()
            if source is None:
                source = JobSource(name=name, **kwargs)
                session.add(source)
                await session.commit()
                await session.refresh(source)
            return source

    async def get_enabled_sources(self) -> Sequence[JobSource]:
        """Obtiene las fuentes habilitadas."""
        async with self._db.session() as session:
            result = await session.execute(
                select(JobSource).where(JobSource.is_enabled == True)  # noqa: E712
            )
            return result.scalars().all()

    async def get_all_sources(self) -> Sequence[JobSource]:
        """Obtiene todas las fuentes."""
        async with self._db.session() as session:
            result = await session.execute(select(JobSource).order_by(JobSource.name))
            return result.scalars().all()

    async def update_source_health(
        self,
        source_id: int,
        *,
        is_healthy: bool,
        response_time_ms: int | None = None,
        jobs_found: int = 0,
        duplicates_found: int = 0,
        error_message: str | None = None,
    ) -> None:
        """Registra un chequeo de salud de una fuente."""
        async with self._db.session() as session:
            # Update source status
            update_values: dict = {
                "last_checked_at": datetime.utcnow(),
            }
            if is_healthy:
                update_values["last_success_at"] = datetime.utcnow()
                update_values["consecutive_errors"] = 0
                update_values["last_error"] = None
                update_values["status"] = "operativa"
            else:
                # Increment consecutive errors
                result = await session.execute(
                    select(JobSource.consecutive_errors).where(JobSource.id == source_id)
                )
                current_errors = result.scalar() or 0
                update_values["consecutive_errors"] = current_errors + 1
                update_values["last_error"] = error_message
                if current_errors + 1 >= 5:
                    update_values["status"] = "fallida"
                else:
                    update_values["status"] = "limitada"

            await session.execute(
                update(JobSource).where(JobSource.id == source_id).values(**update_values)
            )

            # Record health check
            health = SourceHealth(
                source_id=source_id,
                is_healthy=is_healthy,
                response_time_ms=response_time_ms,
                jobs_found=jobs_found,
                duplicates_found=duplicates_found,
                error_message=error_message,
            )
            session.add(health)
            await session.commit()

    # --- Jobs ---

    async def job_exists_by_hash(self, dedup_hash: str) -> bool:
        """Verifica si ya existe una oferta con el mismo hash de deduplicación."""
        async with self._db.session() as session:
            result = await session.execute(
                select(func.count()).select_from(Job).where(Job.dedup_hash == dedup_hash)
            )
            return (result.scalar() or 0) > 0

    async def job_exists_by_source_and_external_id(
        self, source_id: int, external_id: str
    ) -> Job | None:
        """Busca una oferta existente por fuente e ID externo."""
        async with self._db.session() as session:
            result = await session.execute(
                select(Job).where(and_(Job.source_id == source_id, Job.external_id == external_id))
            )
            return result.scalar_one_or_none()

    async def add_job(self, **kwargs) -> Job:
        """Agrega una nueva oferta de empleo."""
        async with self._db.session() as session:
            job = Job(**kwargs)
            session.add(job)
            await session.commit()
            await session.refresh(job)
            logger.info("Nueva oferta agregada: %s en %s", job.title, job.company)
            return job

    async def update_job(self, job_id: int, **kwargs) -> Job | None:
        """Actualiza una oferta existente."""
        async with self._db.session() as session:
            result = await session.execute(select(Job).where(Job.id == job_id))
            job = result.scalar_one_or_none()
            if job:
                changes = []
                for key, value in kwargs.items():
                    if hasattr(job, key):
                        old_value = getattr(job, key)
                        if old_value != value:
                            changes.append((key, str(old_value), str(value)))
                            setattr(job, key, value)
                # Record observations for changes
                for field, old_val, new_val in changes:
                    obs = JobObservation(
                        job_id=job_id,
                        field_changed=field,
                        old_value=old_val,
                        new_value=new_val,
                    )
                    session.add(obs)
                await session.commit()
                await session.refresh(job)
            return job

    async def get_job(self, job_id: int) -> Job | None:
        """Obtiene una oferta por ID."""
        async with self._db.session() as session:
            result = await session.execute(select(Job).where(Job.id == job_id))
            return result.scalar_one_or_none()

    async def get_recent_jobs(
        self,
        limit: int = 20,
        *,
        region: str | None = None,
        comuna: str | None = None,
        status: str | None = None,
    ) -> Sequence[Job]:
        """Obtiene ofertas recientes con filtros opcionales."""
        async with self._db.session() as session:
            query = select(Job)
            conditions = []
            if region:
                conditions.append(Job.region == region)
            if comuna:
                conditions.append(Job.comuna == comuna)
            if status:
                conditions.append(Job.status == status)
            if conditions:
                query = query.where(and_(*conditions))
            query = query.order_by(Job.detected_at.desc()).limit(limit)
            result = await session.execute(query)
            return result.scalars().all()

    async def search_jobs(
        self,
        query_text: str,
        limit: int = 20,
    ) -> Sequence[Job]:
        """Busca ofertas por texto en título, empresa o descripción."""
        async with self._db.session() as session:
            pattern = f"%{query_text}%"
            result = await session.execute(
                select(Job)
                .where(
                    or_(
                        Job.title.ilike(pattern),
                        Job.company.ilike(pattern),
                        Job.description.ilike(pattern),
                    )
                )
                .order_by(Job.detected_at.desc())
                .limit(limit)
            )
            return result.scalars().all()

    async def mark_job_notified(self, job_id: int, message_id: int | None = None) -> None:
        """Marca una oferta como notificada."""
        async with self._db.session() as session:
            await session.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(notified=True, notification_message_id=message_id)
            )
            await session.commit()

    async def get_unnotified_jobs(self) -> Sequence[Job]:
        """Obtiene ofertas que aún no han sido notificadas."""
        async with self._db.session() as session:
            result = await session.execute(
                select(Job)
                .where(Job.notified == False)  # noqa: E712
                .order_by(Job.detected_at.asc())
            )
            return result.scalars().all()

    async def increment_source_jobs_count(self, source_id: int, count: int = 1) -> None:
        """Incrementa el contador de ofertas encontradas de una fuente."""
        async with self._db.session() as session:
            await session.execute(
                update(JobSource)
                .where(JobSource.id == source_id)
                .values(total_jobs_found=JobSource.total_jobs_found + count)
            )
            await session.commit()

    # --- Saved Jobs ---

    async def save_job(self, owner_id: int, job_id: int, notes: str | None = None) -> SavedJob:
        """Guarda una oferta para el usuario."""
        async with self._db.session() as session:
            existing = await session.execute(
                select(SavedJob).where(
                    and_(SavedJob.owner_id == owner_id, SavedJob.job_id == job_id)
                )
            )
            if existing.scalar_one_or_none():
                raise ValueError("Esta oferta ya está guardada")
            saved = SavedJob(owner_id=owner_id, job_id=job_id, notes=notes)
            session.add(saved)
            await session.commit()
            await session.refresh(saved)
            return saved

    async def get_saved_jobs(self, owner_id: int) -> Sequence[SavedJob]:
        """Obtiene las ofertas guardadas."""
        async with self._db.session() as session:
            result = await session.execute(
                select(SavedJob)
                .where(SavedJob.owner_id == owner_id)
                .order_by(SavedJob.saved_at.desc())
            )
            return result.scalars().all()

    # --- Applications ---

    async def create_application(self, owner_id: int, job_id: int) -> Application:
        """Crea una nueva postulación."""
        async with self._db.session() as session:
            existing = await session.execute(
                select(Application).where(
                    and_(Application.owner_id == owner_id, Application.job_id == job_id)
                )
            )
            if existing.scalar_one_or_none():
                raise ValueError("Ya existe una postulación para esta oferta")
            app = Application(owner_id=owner_id, job_id=job_id)
            session.add(app)
            await session.commit()
            await session.refresh(app)
            return app

    async def get_application(self, application_id: int) -> Application | None:
        """Obtiene una postulación por ID."""
        async with self._db.session() as session:
            result = await session.execute(
                select(Application).where(Application.id == application_id)
            )
            return result.scalar_one_or_none()

    async def get_application_for_job(self, owner_id: int, job_id: int) -> Application | None:
        """Obtiene la postulación para una oferta específica."""
        async with self._db.session() as session:
            result = await session.execute(
                select(Application).where(
                    and_(Application.owner_id == owner_id, Application.job_id == job_id)
                )
            )
            return result.scalar_one_or_none()

    async def update_application_status(
        self, application_id: int, status: str, detail: str | None = None
    ) -> None:
        """Actualiza el estado de una postulación y registra el evento."""
        async with self._db.session() as session:
            await session.execute(
                update(Application)
                .where(Application.id == application_id)
                .values(status=status, updated_at=datetime.utcnow())
            )
            event = ApplicationEvent(
                application_id=application_id,
                event_type=f"status_change:{status}",
                detail=detail,
            )
            session.add(event)
            await session.commit()

    async def get_applications(
        self,
        owner_id: int,
        *,
        status: str | None = None,
        limit: int = 20,
    ) -> Sequence[Application]:
        """Lista postulaciones con filtros opcionales."""
        async with self._db.session() as session:
            query = select(Application).where(Application.owner_id == owner_id)
            if status:
                query = query.where(Application.status == status)
            query = query.order_by(Application.updated_at.desc()).limit(limit)
            result = await session.execute(query)
            return result.scalars().all()

    # --- Application Answers ---

    async def save_application_answer(
        self,
        application_id: int,
        question: str,
        answer: str,
        source: str = "manual",
    ) -> ApplicationAnswer:
        """Guarda una respuesta de postulación."""
        async with self._db.session() as session:
            app_answer = ApplicationAnswer(
                application_id=application_id,
                question=question,
                answer=answer,
                source=source,
            )
            session.add(app_answer)
            await session.commit()
            await session.refresh(app_answer)
            return app_answer

    async def get_application_answers(self, application_id: int) -> Sequence[ApplicationAnswer]:
        """Obtiene las respuestas de una postulación."""
        async with self._db.session() as session:
            result = await session.execute(
                select(ApplicationAnswer)
                .where(ApplicationAnswer.application_id == application_id)
                .order_by(ApplicationAnswer.id)
            )
            return result.scalars().all()

    # --- Reusable Answers ---

    async def save_reusable_answer(
        self,
        profile_id: int,
        question_key: str,
        question_text: str,
        answer_text: str,
    ) -> ReusableAnswer:
        """Guarda o actualiza una respuesta reutilizable."""
        async with self._db.session() as session:
            result = await session.execute(
                select(ReusableAnswer).where(
                    and_(
                        ReusableAnswer.profile_id == profile_id,
                        ReusableAnswer.question_key == question_key,
                    )
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.answer_text = answer_text
                existing.question_text = question_text
                existing.updated_at = datetime.utcnow()
                await session.commit()
                await session.refresh(existing)
                return existing
            answer = ReusableAnswer(
                profile_id=profile_id,
                question_key=question_key,
                question_text=question_text,
                answer_text=answer_text,
            )
            session.add(answer)
            await session.commit()
            await session.refresh(answer)
            return answer

    async def get_reusable_answers(self, profile_id: int) -> Sequence[ReusableAnswer]:
        """Obtiene todas las respuestas reutilizables."""
        async with self._db.session() as session:
            result = await session.execute(
                select(ReusableAnswer)
                .where(ReusableAnswer.profile_id == profile_id)
                .order_by(ReusableAnswer.question_key)
            )
            return result.scalars().all()

    # --- Notifications ---

    async def add_notification(
        self,
        owner_id: int,
        notification_type: str,
        job_id: int | None = None,
        message_id: int | None = None,
        channel_id: int | None = None,
        content_preview: str | None = None,
    ) -> Notification:
        """Registra una notificación enviada."""
        async with self._db.session() as session:
            notif = Notification(
                owner_id=owner_id,
                notification_type=notification_type,
                job_id=job_id,
                message_id=message_id,
                channel_id=channel_id,
                content_preview=content_preview,
            )
            session.add(notif)
            await session.commit()
            await session.refresh(notif)
            return notif

    # --- Migrations ---

    async def record_migration(self, version: str, description: str) -> None:
        """Registra una migración aplicada."""
        async with self._db.session() as session:
            migration = SchemaMigration(version=version, description=description)
            session.add(migration)
            await session.commit()

    async def get_applied_migrations(self) -> Sequence[SchemaMigration]:
        """Obtiene las migraciones aplicadas."""
        async with self._db.session() as session:
            result = await session.execute(
                select(SchemaMigration).order_by(SchemaMigration.version)
            )
            return result.scalars().all()

    # --- Statistics ---

    async def get_job_stats(self) -> dict:
        """Obtiene estadísticas generales de ofertas."""
        async with self._db.session() as session:
            total = await session.execute(select(func.count()).select_from(Job))
            active = await session.execute(
                select(func.count()).select_from(Job).where(Job.status == "activa")
            )
            notified = await session.execute(
                select(func.count()).select_from(Job).where(Job.notified == True)  # noqa: E712
            )
            return {
                "total": total.scalar() or 0,
                "active": active.scalar() or 0,
                "notified": notified.scalar() or 0,
            }

    async def get_application_stats(self, owner_id: int) -> dict:
        """Obtiene estadísticas de postulaciones."""
        async with self._db.session() as session:
            result = await session.execute(
                select(Application.status, func.count())
                .where(Application.owner_id == owner_id)
                .group_by(Application.status)
            )
            stats = {row[0]: row[1] for row in result.all()}
            return stats
