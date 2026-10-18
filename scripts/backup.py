"""Script seguro de copias de seguridad (Backup) para EmpleoRadar."""

from __future__ import annotations

import argparse
import datetime
import tarfile
from pathlib import Path


def create_backup(
    db_file: Path | str = "data/empleoradar.db",
    cv_dir: Path | str = "data/private/resumes",
    backup_dir: Path | str = "data/backups",
) -> Path:
    """Empaqueta la base de datos y los currículums privados en un archivo tar.gz seguro."""
    db_path = Path(db_file)
    cv_path = Path(cv_dir)
    b_dir = Path(backup_dir)
    b_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = b_dir / f"empleoradar_backup_{timestamp}.tar.gz"

    with tarfile.open(backup_filename, "w:gz") as tar:
        if db_path.exists():
            tar.add(db_path, arcname="database/empleoradar.db")
            print(f"✅ Base de datos incluida: {db_path}")
        else:
            print(f"⚠️ Base de datos no encontrada en {db_path}")

        if cv_path.exists():
            tar.add(cv_path, arcname="resumes")
            print(f"✅ Directorio de CVs incluido: {cv_path}")
        else:
            print(f"⚠️ Directorio de CVs no encontrado en {cv_path}")

    print(f"\n🎉 Respaldo creado exitosamente: {backup_filename}")
    print(f"📦 Tamaño del respaldo: {backup_filename.stat().st_size // 1024} KB")
    return backup_filename


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crear respaldo de EmpleoRadar")
    parser.add_argument("--db", default="data/empleoradar.db", help="Ruta a la base de datos")
    parser.add_argument("--resumes", default="data/private/resumes", help="Ruta a los CVs")
    parser.add_argument("--dest", default="data/backups", help="Directorio destino")
    args = parser.parse_args()

    create_backup(args.db, args.resumes, args.dest)
