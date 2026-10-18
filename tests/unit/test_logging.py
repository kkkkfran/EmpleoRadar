"""Pruebas unitarias para el sistema de logging y filtro de redacción."""

import logging

from app.logging_config import RedactingFilter


def test_redacting_filter_hides_tokens_passwords_and_emails():
    filt = RedactingFilter()

    # Log record con token
    record1 = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Iniciando conexión con token='MTAxMjM0NTY3ODkw.SECRET_TOKEN_XYZ'",
        args=(),
        exc_info=None,
    )
    filt.filter(record1)
    assert "[REDACTED]" in record1.msg
    assert "SECRET_TOKEN_XYZ" not in record1.msg

    # Log record con email
    record2 = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Notificación enviada a postulante@gmail.com con éxito",
        args=(),
        exc_info=None,
    )
    filt.filter(record2)
    assert "[EMAIL_REDACTED]" in record2.msg
    assert "postulante@gmail.com" not in record2.msg

    # Log record con teléfono chileno
    record3 = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Contacto registrado: +56 9 8765 4321",
        args=(),
        exc_info=None,
    )
    filt.filter(record3)
    assert "[PHONE_REDACTED]" in record3.msg
