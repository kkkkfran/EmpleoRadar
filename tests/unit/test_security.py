"""Pruebas unitarias para utilidades de seguridad, mitigación SSRF y redacción."""

from app.security.permissions import is_owner
from app.security.redaction import is_safe_url, redact_email, redact_token, sanitize_filename


def test_ssrf_protection_blocks_private_networks():
    # Redes locales y privadas prohibidas
    assert is_safe_url("http://127.0.0.1:8000/api") is False
    assert is_safe_url("http://localhost:5000/info") is False
    assert is_safe_url("http://192.168.1.1/admin") is False
    assert is_safe_url("http://10.0.0.5/") is False
    assert is_safe_url("http://172.16.0.1/") is False
    assert is_safe_url("http://169.254.169.254/latest/meta-data/") is False  # AWS/Cloud metadata
    assert is_safe_url("ftp://chiletrabajos.cl/ofertas") is False  # Esquema inválido

    # URLs públicas permitidas
    assert is_safe_url("https://www.chiletrabajos.cl/rss/") is True
    assert is_safe_url("https://www.bne.gob.cl/ofertas") is True
    assert is_safe_url("https://cl.indeed.com/") is True


def test_redact_token():
    token = "MTA1NzY1NDMyMTA5ODc2NTQzMg.G12345.abcdefghijklmnopqrstuvwxyz"
    redacted = redact_token(token, visible_chars=4)
    assert redacted.startswith("MTA1...")
    assert "[REDACTED]" in redacted
    assert "abcdefghijklmnopqrstuvwxyz" not in redacted


def test_redact_email():
    assert redact_email("usuario.ejemplo@gmail.com") == "u*************o@gmail.com"
    assert redact_email("yo@dominio.cl") == "**@dominio.cl"


def test_sanitize_filename():
    assert sanitize_filename("../../etc/passwd") == "______etc_passwd"
    assert sanitize_filename("mi_cv\0_privado.pdf") == "mi_cv_privado.pdf"
    assert (
        sanitize_filename("  Curriculum (Chillán) - 2026.pdf  ")
        == "Curriculum (Chillán) - 2026.pdf"
    )


def test_is_owner_check():
    class DummyClient:
        owner_id = 998877

    class DummyUser:
        id = 998877

    class DummyInteraction:
        client = DummyClient()
        user = DummyUser()

    inter = DummyInteraction()
    assert is_owner(inter) is True

    # Usuario no autorizado
    inter.user.id = 111111
    assert is_owner(inter) is False
