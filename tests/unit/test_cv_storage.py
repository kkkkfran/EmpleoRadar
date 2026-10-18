"""Pruebas unitarias para almacenamiento, seguridad y extracción de texto de CVs."""

import io

import pypdf
import pytest

from app.profile.cv_storage import CVStorage, CVStorageError


def create_minimal_pdf_bytes(text: str = "Currículum Vitae - Ingeniero en Informática") -> bytes:
    """Genera bytes de un PDF válido mínimo para pruebas."""
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=612, height=792)
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


def test_validate_non_pdf_fails(tmp_path):
    storage = CVStorage(tmp_path)
    with pytest.raises(CVStorageError, match="Solo se admiten archivos PDF"):
        storage.validate_file("documento.docx", b"PK\x03\x04...")


def test_validate_invalid_pdf_header_fails(tmp_path):
    storage = CVStorage(tmp_path)
    with pytest.raises(CVStorageError, match="no es un documento PDF válido"):
        storage.validate_file("cv.pdf", b"NOT_A_PDF_CONTENT")


def test_validate_size_limit_fails(tmp_path):
    storage = CVStorage(tmp_path)
    large_bytes = b"%PDF" + b"0" * (11 * 1024 * 1024)  # 11 MB
    with pytest.raises(CVStorageError, match="excede el tamaño máximo"):
        storage.validate_file("cv.pdf", large_bytes)


def test_save_and_extract_cv(tmp_path):
    storage = CVStorage(tmp_path)
    pdf_bytes = create_minimal_pdf_bytes()

    stored_name, f_hash, f_size, extracted = storage.save_cv(
        owner_id=12345,
        filename="Mi_Curriculum.pdf",
        content=pdf_bytes,
    )

    assert stored_name.startswith("cv_12345_")
    assert len(f_hash) == 64
    assert f_size == len(pdf_bytes)
    assert (tmp_path / stored_name).exists()

    # Obtener ruta segura
    path = storage.get_cv_path(stored_name)
    assert path.exists()

    # Eliminar
    deleted = storage.delete_cv(stored_name)
    assert deleted is True
    assert not (tmp_path / stored_name).exists()


def test_path_traversal_protection(tmp_path):
    storage = CVStorage(tmp_path)
    with pytest.raises(CVStorageError):
        storage.get_cv_path("../../../windows/system32/cmd.exe")
