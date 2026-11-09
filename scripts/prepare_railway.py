"""Prepara variables privadas y una copia consistente de SQLite sin mostrar secretos.

Ejecutar desde la raíz: python -m scripts.prepare_railway
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

from app.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def prepare_railway(root: Path = PROJECT_ROOT, *, include_token: bool = True) -> tuple[Path, Path | None]:
    values = {key: value for key, value in dotenv_values(root / ".env").items() if value}
    settings = Settings(_env_file=None, **{key.lower(): value for key, value in values.items()})
    values.update({
        "DISCORD_BOT_TOKEN": settings.discord_bot_token if include_token else "",
        "DISCORD_OWNER_ID": str(settings.discord_owner_id),
        "DISCORD_CHANNEL_INFORMATICA_ID": str(settings.discord_channel_informatica_id),
        "DISCORD_CHANNEL_CHILLAN_ID": str(settings.discord_channel_chillan_id),
        "DATABASE_URL": "sqlite+aiosqlite:////app/data/empleoradar.db",
        "CV_STORAGE_DIR": "/app/data/private/resumes",
        "BACKUP_DIR": "/app/data/backups",
        "POLL_INTERVAL_MINUTES": "2",
        "RECOVERY_DAYS": "4",
        "MAX_CONCURRENT_REQUESTS": "3",
        "REQUEST_TIMEOUT_SECONDS": "30",
        "SOURCE_TIMEOUT_SECONDS": "180",
        "TIMEZONE": "America/Santiago",
        # Los volúmenes de Railway se montan como root (documentación oficial).
        "RAILWAY_RUN_UID": "0",
    })
    values.pop("PORT", None)  # Lo asigna Railway.
    output = root / ".env.railway.local"
    output.write_text(
        "# PRIVADO: pegar en Railway > Variables > Raw Editor. No subir a Git.\n"
        + "\n".join(f"{key}={json.dumps(value, ensure_ascii=False)}" for key, value in values.items())
        + "\n",
        encoding="utf-8",
    )
    db_url = make_url(settings.database_url)
    snapshot = None
    if db_url.get_backend_name() == "sqlite" and db_url.database != ":memory:":
        source = Path(db_url.database or "")
        if not source.is_absolute():
            source = root / source
        if source.is_file():
            snapshot = root / "data/backups/railway/empleoradar.db"
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            with (
                closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as original,
                closing(sqlite3.connect(snapshot)) as backup,
            ):
                original.backup(backup)
    return output, snapshot


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--omit-token", action="store_true", help="Deja vacío un token revocado o inválido.")
    args = parser.parse_args()
    env_file, database_copy = prepare_railway(include_token=not args.omit_token)
    print(f"Variables privadas preparadas: {env_file}")
    if database_copy:
        print(f"Copia consistente de la base local: {database_copy}")
    print("No se mostraron credenciales ni se modificó la base original.")
