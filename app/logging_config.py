"""Configuración de logging estructurado para EmpleoRadar."""

from __future__ import annotations

import logging
import logging.handlers
import re
from pathlib import Path

# Patterns to redact from logs
_REDACT_PATTERNS = [
    (re.compile(r'(token["\']?\s*[:=]\s*["\']?)[\w\-.]+', re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r'(password["\']?\s*[:=]\s*["\']?)[^\s"\',]+', re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r'(secret["\']?\s*[:=]\s*["\']?)[^\s"\',]+', re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(Bearer\s+)[\w\-.]+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(\+?56\s?\d{1}\s?\d{4}\s?\d{4})"), "[PHONE_REDACTED]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL_REDACTED]"),
]


class RedactingFilter(logging.Filter):
    """Filtro que redacta información sensible de los logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern, replacement in _REDACT_PATTERNS:
                record.msg = pattern.sub(replacement, record.msg)
        if record.args:
            new_args = []
            for arg in record.args if isinstance(record.args, tuple) else (record.args,):
                if isinstance(arg, str):
                    for pattern, replacement in _REDACT_PATTERNS:
                        arg = pattern.sub(replacement, arg)
                new_args.append(arg)
            record.args = tuple(new_args)
        return True


def setup_logging(level: str = "INFO", log_dir: str | Path = "logs") -> None:
    """Configura el sistema de logging con rotación y redacción."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers
    root_logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(RedactingFilter())
    root_logger.addHandler(console_handler)

    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_path / "empleoradar.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(RedactingFilter())
    root_logger.addHandler(file_handler)

    # Reduce noise from libraries
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
