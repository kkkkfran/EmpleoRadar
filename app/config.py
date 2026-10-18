"""Configuración central de EmpleoRadar."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuración del bot cargada desde variables de entorno."""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # Discord
    discord_bot_token: str = Field(..., description="Token del bot de Discord")
    discord_owner_id: int = Field(..., description="ID del propietario del bot")
    discord_guild_id: int | None = Field(default=None, description="ID del servidor de Discord")

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///data/empleoradar.db",
        description="URL de conexión a la base de datos",
    )

    # Timezone
    timezone: str = Field(default="America/Santiago")

    # Logging
    log_level: str = Field(default="INFO")

    # Job sources
    poll_interval_minutes: int = Field(default=15, ge=1, le=1440)
    max_concurrent_requests: int = Field(default=3, ge=1, le=10)
    request_timeout_seconds: int = Field(default=30, ge=5, le=120)

    # CV Storage
    cv_storage_dir: str = Field(default="data/private/resumes")

    # Applications
    application_require_confirmation: bool = Field(default=True)

    # Backup
    backup_dir: str = Field(default="data/backups")

    # Derived paths
    @property
    def base_dir(self) -> Path:
        """Directorio raíz del proyecto."""
        return Path(__file__).resolve().parent.parent

    @property
    def cv_storage_path(self) -> Path:
        """Ruta absoluta al directorio de CVs."""
        p = Path(self.cv_storage_dir)
        if not p.is_absolute():
            p = self.base_dir / p
        return p

    @property
    def backup_path(self) -> Path:
        """Ruta absoluta al directorio de backups."""
        p = Path(self.backup_dir)
        if not p.is_absolute():
            p = self.base_dir / p
        return p

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v = v.upper()
        if v not in valid:
            raise ValueError(f"log_level debe ser uno de: {valid}")
        return v

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v:
            raise ValueError("DATABASE_URL no puede estar vacío")
        return v

    def ensure_directories(self) -> None:
        """Crea los directorios necesarios si no existen."""
        self.cv_storage_path.mkdir(parents=True, exist_ok=True)
        self.backup_path.mkdir(parents=True, exist_ok=True)
        # Ensure data directory for SQLite
        db_path = self.database_url
        if "sqlite" in db_path:
            parts = db_path.split("///")
            if len(parts) > 1:
                db_file = Path(parts[1])
                if not db_file.is_absolute():
                    db_file = self.base_dir / db_file
                db_file.parent.mkdir(parents=True, exist_ok=True)
        # Logs directory
        (self.base_dir / "logs").mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    """Obtiene la configuración validada."""
    try:
        return Settings()
    except Exception as e:
        missing = []
        for field_name, field_info in Settings.model_fields.items():
            env_name = field_name.upper()
            if field_info.is_required() and not os.environ.get(env_name):
                missing.append(env_name)
        if missing:
            raise SystemExit(
                f"Variables de entorno requeridas no configuradas: {', '.join(missing)}\n"
                f"Copia .env.example a .env y completa los valores."
            ) from e
        raise
