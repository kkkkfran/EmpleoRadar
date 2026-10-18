"""Pruebas unitarias para los scripts de respaldo y restauración."""

from scripts.backup import create_backup
from scripts.restore import restore_backup


def test_backup_and_restore_cycle(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "empleoradar.db"
    db_file.write_text("DUMMY_DATABASE_CONTENT")

    resumes_dir = data_dir / "private" / "resumes"
    resumes_dir.mkdir(parents=True)
    (resumes_dir / "cv_1.pdf").write_bytes(b"%PDF_CONTENT_TEST")

    backup_dir = tmp_path / "backups"
    backup_file = create_backup(
        db_file=db_file,
        cv_dir=resumes_dir,
        backup_dir=backup_dir,
    )
    assert backup_file.exists()
    assert backup_file.stat().st_size > 0

    # Simular pérdida de datos y restauración
    restore_target = tmp_path / "restored_data"
    restore_backup(backup_file, restore_target)

    assert (restore_target / "database" / "empleoradar.db").exists()
    assert (restore_target / "resumes" / "cv_1.pdf").exists()
    assert (restore_target / "database" / "empleoradar.db").read_text() == "DUMMY_DATABASE_CONTENT"
