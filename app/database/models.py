"""Modelos de base de datos para EmpleoRadar."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


# --- Enums ---


class WorkModality(enum.StrEnum):
    PRESENCIAL = "presencial"
    REMOTO = "remoto"
    HIBRIDO = "hibrido"
    DESCONOCIDO = "desconocido"


class ContractType(enum.StrEnum):
    INDEFINIDO = "indefinido"
    PLAZO_FIJO = "plazo_fijo"
    OBRA_O_PROYECTO = "obra_o_proyecto"
    HONORARIOS = "honorarios"
    PART_TIME = "part_time"
    PRACTICA = "practica"
    DESCONOCIDO = "desconocido"


class WorkSchedule(enum.StrEnum):
    COMPLETA = "completa"
    PARCIAL = "parcial"
    TURNOS = "turnos"
    DESCONOCIDO = "desconocido"


class JobStatus(enum.StrEnum):
    ACTIVA = "activa"
    EXPIRADA = "expirada"
    ELIMINADA = "eliminada"
    DESCONOCIDO = "desconocido"


class SourceStatus(enum.StrEnum):
    OPERATIVA = "operativa"
    LIMITADA = "limitada"
    PENDIENTE = "pendiente"
    DESACTIVADA = "desactivada"
    FALLIDA = "fallida"


class ApplicationStatus(enum.StrEnum):
    DETECTADA = "detectada"
    GUARDADA = "guardada"
    EN_PREPARACION = "en_preparacion"
    PENDIENTE_RESPUESTAS = "pendiente_respuestas"
    LISTA_PARA_REVISAR = "lista_para_revisar"
    PENDIENTE_CONFIRMACION = "pendiente_confirmacion"
    ENVIANDO = "enviando"
    ENVIADA_CONFIRMADA = "enviada_confirmada"
    REQUIERE_INTERVENCION = "requiere_intervencion"
    FALLIDA = "fallida"
    CANCELADA = "cancelada"


class NotificationType(enum.StrEnum):
    NUEVA_OFERTA = "nueva_oferta"
    OFERTA_ACTUALIZADA = "oferta_actualizada"
    FUENTE_ERROR = "fuente_error"
    RECORDATORIO = "recordatorio"
    SISTEMA = "sistema"


# --- Models ---


class Owner(Base):
    __tablename__ = "owners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discord_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    profile: Mapped[CandidateProfile | None] = relationship(back_populates="owner", uselist=False)
    preferences: Mapped[CandidatePreferences | None] = relationship(
        back_populates="owner", uselist=False
    )
    resumes: Mapped[list[Resume]] = relationship(back_populates="owner")
    saved_jobs: Mapped[list[SavedJob]] = relationship(back_populates="owner")
    applications: Mapped[list[Application]] = relationship(back_populates="owner")
    notifications: Mapped[list[Notification]] = relationship(back_populates="owner")


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("owners.id"), unique=True, nullable=False
    )
    education: Mapped[str | None] = mapped_column(
        Text
    )  # JSON: [{degree, institution, status, year}]
    work_experience: Mapped[str | None] = mapped_column(
        Text
    )  # JSON: [{company, role, start, end, functions}]
    technologies: Mapped[str | None] = mapped_column(Text)  # JSON: [str]
    projects: Mapped[str | None] = mapped_column(Text)  # JSON: [{name, description, url}]
    certifications: Mapped[str | None] = mapped_column(Text)  # JSON: [{name, issuer, year}]
    excel_level: Mapped[str | None] = mapped_column(String(50))
    drivers_license: Mapped[str | None] = mapped_column(String(20))
    own_transport: Mapped[bool | None] = mapped_column(Boolean)
    availability: Mapped[str | None] = mapped_column(String(200))
    salary_expectation_min: Mapped[int | None] = mapped_column(Integer)
    salary_expectation_max: Mapped[int | None] = mapped_column(Integer)
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(200))
    preferred_contract: Mapped[str | None] = mapped_column(String(50))
    preferred_schedule: Mapped[str | None] = mapped_column(String(50))
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped[Owner] = relationship(back_populates="profile")
    answers: Mapped[list[ReusableAnswer]] = relationship(back_populates="profile")


class ReusableAnswer(Base):
    __tablename__ = "reusable_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("candidate_profiles.id"), nullable=False
    )
    question_key: Mapped[str] = mapped_column(String(200), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    profile: Mapped[CandidateProfile] = relationship(back_populates="answers")

    __table_args__ = (UniqueConstraint("profile_id", "question_key", name="uq_profile_question"),)


class CandidatePreferences(Base):
    __tablename__ = "candidate_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("owners.id"), unique=True, nullable=False
    )
    preferred_regions: Mapped[str | None] = mapped_column(Text)  # JSON: [str]
    preferred_comunas: Mapped[str | None] = mapped_column(Text)  # JSON: [str]
    priority_comunas: Mapped[str | None] = mapped_column(Text)  # JSON: [str] - higher priority
    interest_areas: Mapped[str | None] = mapped_column(Text)  # JSON: [str]
    interest_keywords: Mapped[str | None] = mapped_column(Text)  # JSON: [str]
    exclude_internships: Mapped[bool] = mapped_column(Boolean, default=True)
    exclude_thesis: Mapped[bool] = mapped_column(Boolean, default=True)
    min_salary: Mapped[int | None] = mapped_column(Integer)
    preferred_modality: Mapped[str | None] = mapped_column(String(50))
    preferred_contract: Mapped[str | None] = mapped_column(String(50))
    preferred_schedule: Mapped[str | None] = mapped_column(String(50))
    min_score_notify: Mapped[int] = mapped_column(Integer, default=30)  # Min score to notify
    # Scoring weights (0.0-1.0)
    weight_location: Mapped[float] = mapped_column(Float, default=0.25)
    weight_skills: Mapped[float] = mapped_column(Float, default=0.25)
    weight_experience: Mapped[float] = mapped_column(Float, default=0.15)
    weight_education: Mapped[float] = mapped_column(Float, default=0.10)
    weight_modality: Mapped[float] = mapped_column(Float, default=0.10)
    weight_contract: Mapped[float] = mapped_column(Float, default=0.05)
    weight_salary: Mapped[float] = mapped_column(Float, default=0.10)
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    notification_channel_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel_informatica_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel_chillan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped[Owner] = relationship(back_populates="preferences")


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("owners.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str | None] = mapped_column(String(100))  # e.g., "Desarrollo", "Soporte TI"
    extracted_text: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    owner: Mapped[Owner] = relationship(back_populates="resumes")


class JobSource(Base):
    __tablename__ = "job_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    url: Mapped[str | None] = mapped_column(String(500))
    source_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # api, rss, scraper, manual
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default=SourceStatus.PENDIENTE.value)
    poll_interval_minutes: Mapped[int] = mapped_column(Integer, default=15)
    requires_auth: Mapped[bool] = mapped_column(Boolean, default=False)
    access_notes: Mapped[str | None] = mapped_column(Text)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime)
    consecutive_errors: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    total_jobs_found: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    jobs: Mapped[list[Job]] = relationship(back_populates="source")
    health_records: Mapped[list[SourceHealth]] = relationship(back_populates="source")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("job_sources.id"), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    company: Mapped[str | None] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(300))
    region: Mapped[str | None] = mapped_column(String(100))
    comuna: Mapped[str | None] = mapped_column(String(100))
    modality: Mapped[str] = mapped_column(String(20), default=WorkModality.DESCONOCIDO.value)
    contract_type: Mapped[str] = mapped_column(String(30), default=ContractType.DESCONOCIDO.value)
    schedule: Mapped[str] = mapped_column(String(20), default=WorkSchedule.DESCONOCIDO.value)
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_type: Mapped[str | None] = mapped_column(String(20))  # bruto, liquido, null
    requirements: Mapped[str | None] = mapped_column(Text)
    experience_required: Mapped[str | None] = mapped_column(String(200))
    education_required: Mapped[str | None] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    detected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    status: Mapped[str] = mapped_column(String(20), default=JobStatus.ACTIVA.value)
    is_internship: Mapped[bool] = mapped_column(Boolean, default=False)
    dedup_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 dedup fingerprint
    raw_data: Mapped[str | None] = mapped_column(Text)  # JSON original data
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    notification_message_id: Mapped[int | None] = mapped_column(Integer)

    source: Mapped[JobSource] = relationship(back_populates="jobs")
    observations: Mapped[list[JobObservation]] = relationship(back_populates="job")
    saved_by: Mapped[list[SavedJob]] = relationship(back_populates="job")
    applications: Mapped[list[Application]] = relationship(back_populates="job")

    __table_args__ = (
        Index("ix_jobs_dedup_hash", "dedup_hash"),
        Index("ix_jobs_source_external", "source_id", "external_id"),
        Index("ix_jobs_detected_at", "detected_at"),
        Index("ix_jobs_region_comuna", "region", "comuna"),
        Index("ix_jobs_status", "status"),
    )


class JobObservation(Base):
    __tablename__ = "job_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id"), nullable=False)
    field_changed: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    job: Mapped[Job] = relationship(back_populates="observations")


class SavedJob(Base):
    __tablename__ = "saved_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("owners.id"), nullable=False)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id"), nullable=False)
    saved_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    notes: Mapped[str | None] = mapped_column(Text)

    owner: Mapped[Owner] = relationship(back_populates="saved_jobs")
    job: Mapped[Job] = relationship(back_populates="saved_by")

    __table_args__ = (UniqueConstraint("owner_id", "job_id", name="uq_saved_job"),)


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("owners.id"), nullable=False)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id"), nullable=False)
    resume_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("resumes.id"))
    status: Mapped[str] = mapped_column(String(30), default=ApplicationStatus.DETECTADA.value)
    submission_method: Mapped[str | None] = mapped_column(String(50))  # portal, email, manual
    confirmation_id: Mapped[str | None] = mapped_column(String(200))
    confirmation_detail: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    next_action: Mapped[str | None] = mapped_column(String(300))
    next_action_date: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)

    owner: Mapped[Owner] = relationship(back_populates="applications")
    job: Mapped[Job] = relationship(back_populates="applications")
    answers: Mapped[list[ApplicationAnswer]] = relationship(back_populates="application")
    events: Mapped[list[ApplicationEvent]] = relationship(back_populates="application")

    __table_args__ = (
        UniqueConstraint("owner_id", "job_id", name="uq_application_job"),
        Index("ix_applications_status", "status"),
    )


class ApplicationAnswer(Base):
    __tablename__ = "application_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("applications.id"), nullable=False
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    is_draft: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(50), default="manual")  # manual, profile, reusable
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    application: Mapped[Application] = relationship(back_populates="answers")


class ApplicationEvent(Base):
    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("applications.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    application: Mapped[Application] = relationship(back_populates="events")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("owners.id"), nullable=False)
    notification_type: Mapped[str] = mapped_column(String(30), nullable=False)
    job_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("jobs.id"))
    message_id: Mapped[int | None] = mapped_column(Integer)  # Discord message ID
    channel_id: Mapped[int | None] = mapped_column(Integer)
    content_preview: Mapped[str | None] = mapped_column(String(500))
    sent_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)

    owner: Mapped[Owner] = relationship(back_populates="notifications")


class SourceHealth(Base):
    __tablename__ = "source_health"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("job_sources.id"), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    is_healthy: Mapped[bool] = mapped_column(Boolean, nullable=False)
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    jobs_found: Mapped[int] = mapped_column(Integer, default=0)
    duplicates_found: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)

    source: Mapped[JobSource] = relationship(back_populates="health_records")


class SchemaMigration(Base):
    __tablename__ = "schema_migrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
