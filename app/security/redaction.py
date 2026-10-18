"""Utilidades para redactar información sensible."""

from __future__ import annotations

import re
from urllib.parse import urlparse

# Private networks that should not be accessed (SSRF protection)
_PRIVATE_NETWORKS = [
    re.compile(r"^127\."),
    re.compile(r"^10\."),
    re.compile(r"^172\.(1[6-9]|2[0-9]|3[01])\."),
    re.compile(r"^192\.168\."),
    re.compile(r"^0\."),
    re.compile(r"^169\.254\."),
    re.compile(r"^fc00:"),
    re.compile(r"^fe80:"),
    re.compile(r"^::1$"),
    re.compile(r"^localhost$", re.IGNORECASE),
]


def redact_token(token: str, visible_chars: int = 4) -> str:
    """Redacta un token mostrando solo los primeros caracteres."""
    if len(token) <= visible_chars:
        return "[REDACTED]"
    return token[:visible_chars] + "..." + "[REDACTED]"


def redact_email(email: str) -> str:
    """Redacta un email preservando el dominio."""
    parts = email.split("@")
    if len(parts) != 2:
        return "[EMAIL_REDACTED]"
    user = parts[0]
    domain = parts[1]
    if len(user) <= 2:
        return f"**@{domain}"
    return f"{user[0]}{'*' * (len(user) - 2)}{user[-1]}@{domain}"


def is_safe_url(url: str) -> bool:
    """Verifica que una URL no apunte a redes privadas (protección SSRF)."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname or ""
        return all(not pattern.match(hostname) for pattern in _PRIVATE_NETWORKS)
    except Exception:
        return False


def sanitize_filename(filename: str) -> str:
    """Sanitiza un nombre de archivo eliminando caracteres peligrosos."""
    filename = filename.strip()
    # Remove path separators and null bytes
    filename = filename.replace("/", "_").replace("\\", "_").replace("\0", "")
    # Remove traversal dots
    filename = filename.replace("..", "__")
    # Remove leading dots (hidden files)
    filename = filename.lstrip(".")
    # Keep only safe characters
    filename = re.sub(r"[^\w.\-() ]", "_", filename)
    # Limit length
    if len(filename) > 200:
        name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
        filename = name[:195] + ("." + ext if ext else "")
    return filename or "unnamed"
