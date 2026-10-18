"""Script de restauración de datos a partir de un respaldo comprimido."""

from __future__ import annotations

import argparse
import tarfile
from pathlib import Path


def restore_backup(
    backup_file: Path | str,
    target_data_dir: Path | str = "data",
) -> None:
    """Extrae y restaura la base de datos y currículums desde un archivo tar.gz."""
    archive_path = Path(backup_file)
    if not archive_path.exists():
        raise FileNotFoundError(f"El archivo de respaldo {archive_path} no existe.")

    target_dir = Path(target_data_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    print(f"Iniciando restauración desde {archive_path} hacia {target_dir}...")
    with tarfile.open(archive_path, "r:gz") as tar:
        # Prevención de ZipSlip / Path Traversal en tar
        for member in tar.getmembers():
            dest = (target_dir / member.name).resolve()
            if not str(dest).startswith(str(target_dir.resolve())):
                raise ValueError(f"Ruta maliciosa detectada en archivo de respaldo: {member.name}")
        tar.extractall(path=target_dir)

    print("✅ Restauración completada exitosamente.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Restaurar respaldo de EmpleoRadar")
    parser.add_argument("archivo", help="Ruta al archivo tar.gz de respaldo")
    parser.add_argument("--dest", default="data", help="Directorio destino")
    args = parser.parse_args()

    restore_backup(args.archivo, args.dest)
