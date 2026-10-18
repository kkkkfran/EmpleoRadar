"""Configuración central de EmpleoRadar."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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

    @field_validator("discord_guild_id", mode="before")
    @classmethod
    def validate_optional_guild_id(cls, v: Any) -> int | None:
        if v is None or v == "" or (isinstance(v, str) and not v.strip()):
            return None
        try:
            return int(v)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"DISCORD_GUILD_ID debe ser un número entero válido (recibido: {v!r})") from exc

    @field_validator("discord_owner_id", mode="before")
    @classmethod
    def validate_owner_id(cls, v: Any) -> int:
        if v is None or v == "" or (isinstance(v, str) and not v.strip()):
            raise ValueError(
                "DISCORD_OWNER_ID no puede estar vacío. Debes ingresar tu ID numérico de usuario de Discord."
            )
        try:
            return int(v)
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"DISCORD_OWNER_ID debe ser un número entero (ejemplo: 123456789012345678, recibido: {v!r})"
            ) from exc

    @field_validator("discord_bot_token", mode="before")
    @classmethod
    def validate_bot_token(cls, v: Any) -> str:
        if v is None or not str(v).strip():
            raise ValueError(
                "DISCORD_BOT_TOKEN no puede estar vacío. Debes ingresar el token de tu bot de Discord."
            )
        return str(v).strip()

    @field_validator("poll_interval_minutes", "max_concurrent_requests", "request_timeout_seconds", mode="before")
    @classmethod
    def validate_optional_numeric(cls, v: Any, info: Any) -> Any:
        if v is None or (isinstance(v, str) and not v.strip()):
            defaults = {
                "poll_interval_minutes": 15,
                "max_concurrent_requests": 3,
                "request_timeout_seconds": 30,
            }
            return defaults.get(info.field_name, v)
        return v

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
        from pydantic import ValidationError

        if isinstance(e, ValidationError):
            err_lines = []
            for err in e.errors():
                loc = " -> ".join(str(item) for item in err.get("loc", []))
                err_lines.append(f"  • {loc.upper()}: {err.get('msg')}")
            details = "\n".join(err_lines)
            raise SystemExit(
                "Faltan variables obligatorias en tu archivo .env:\n"
                f"{details}\n\n"
                "Para solucionarlo:\n"
                "1. Abre tu archivo .env (o cópialo desde .env.example si aún no existe):\n"
                "   copy .env.example .env\n"
                "2. Edita .env con tus credenciales de Discord:\n"
                "   DISCORD_BOT_TOKEN=tu_token_aqui\n"
                "   DISCORD_OWNER_ID=tu_id_numerico_aqui\n"
            ) from e
        raise SystemExit(f"Error al cargar configuración: {e}") from e
