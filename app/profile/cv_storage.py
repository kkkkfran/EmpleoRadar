"""Almacenamiento privado, seguro y extracción de texto de currículums."""

from __future__ import annotations

import hashlib
import io
import logging
import os
from pathlib import Path

import pypdf

from app.security.redaction import sanitize_filename

logger = logging.getLogger(__name__)

# Límite máximo de tamaño de archivo (10 MB)
MAX_CV_SIZE_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf"}


class CVStorageError(Exception):
    """Error durante la gestión de archivos CV."""

    pass


class CVStorage:
    """Gestiona el almacenamiento seguro en disco y extracción de texto de CVs."""

    def __init__(self, storage_dir: Path | str) -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def validate_file(self, filename: str, content: bytes) -> None:
        """Valida tamaño, extensión y cabecera de archivo."""
        if len(content) > MAX_CV_SIZE_BYTES:
            raise CVStorageError(
                f"El archivo excede el tamaño máximo permitido de {MAX_CV_SIZE_BYTES // (1024 * 1024)} MB."
            )

        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise CVStorageError(f"Formato no permitido ({ext}). Solo se admiten archivos PDF.")

        # Verificar 'magic number' de PDF (%PDF)
        if not content.startswith(b"%PDF"):
            raise CVStorageError(
                "El archivo no es un documento PDF válido (cabecera corrupta o inválida)."
            )

    def save_cv(
        self,
        owner_id: int,
        filename: str,
        content: bytes,
    ) -> tuple[str, str, int, str]:
        """Guarda un archivo de CV de forma privada y segura.

        Returns:
            Tuple con (saved_filename, sha256_hash, file_size, extracted_text)
        """
        self.validate_file(filename, content)

        safe_name = sanitize_filename(filename)
        file_hash = hashlib.sha256(content).hexdigest()
        file_size = len(content)

        # Nombre seguro en disco: {owner_id}_{hash[:16]}_{safe_name}
        stored_filename = f"cv_{owner_id}_{file_hash[:16]}_{safe_name}"
        destination = self.storage_dir / stored_filename

        # Evitar path traversal comprobando que la ruta esté dentro del directorio base
        try:
            destination.resolve().relative_to(self.storage_dir.resolve())
        except ValueError as err:
            raise CVStorageError("Ruta de archivo no permitida o potencialmente maliciosa.") from err

        # Escribir archivo
        with open(destination, "wb") as f:
            f.write(content)

        logger.info(
            "CV guardado de forma privada: owner_id=%s, size=%s bytes, hash_prefix=%s",
            owner_id,
            file_size,
            file_hash[:8],
        )

        # Extraer texto del PDF para indexación y asistencia de respuestas
        extracted_text = self.extract_text_from_pdf(content)

        return stored_filename, file_hash, file_size, extracted_text

    def extract_text_from_pdf(self, content: bytes) -> str:
        """Extrae texto legible de un PDF utilizando pypdf de manera segura."""
        try:
            reader = pypdf.PdfReader(io.BytesIO(content))
            extracted_pages = []
            for _i, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    extracted_pages.append(text.strip())
            full_text = "\n\n".join(extracted_pages)
            logger.info(
                "Texto extraído de CV: %d páginas, %d caracteres", len(reader.pages), len(full_text)
            )
            return full_text
        except Exception as e:
            logger.warning(
                "No se pudo extraer texto del PDF (puede estar escaneado o protegido): %s", e
            )
            return ""

    def get_cv_path(self, stored_filename: str) -> Path:
        """Obtiene la ruta absoluta verificada del archivo de CV."""
        safe_name = sanitize_filename(stored_filename)
        path = (self.storage_dir / safe_name).resolve()
        try:
            path.relative_to(self.storage_dir.resolve())
        except ValueError as err:
            raise CVStorageError("Acceso no permitido al archivo de CV.") from err

        if not path.exists():
            raise CVStorageError("El archivo de CV solicitado no existe en el almacenamiento.")
        return path

    def delete_cv(self, stored_filename: str) -> bool:
        """Elimina el archivo del almacenamiento privado."""
        try:
            path = self.get_cv_path(stored_filename)
            if path.exists():
                os.remove(path)
                logger.info("Archivo de CV eliminado: %s", stored_filename)
                return True
        except Exception as e:
            logger.error("Error al eliminar CV %s: %s", stored_filename, e)
        return False
