"""Interfaz base y cliente HTTP resiliente para fuentes de ofertas laborales."""

from __future__ import annotations

import abc
import asyncio
import logging
import time
from datetime import datetime
from typing import Any

import aiohttp

from app.database.models import SourceStatus
from app.jobs.models import JobPayload
from app.security.redaction import is_safe_url

logger = logging.getLogger(__name__)


class SourceError(Exception):
    """Error general ocurrido en una fuente de empleo."""

    pass


class BaseJobSource(abc.ABC):
    """Clase base abstracta para todas las fuentes de ofertas laborales.

    Implementa control de concurrencia, reintentos con backoff exponencial,
    timeouts, verificación de SSRF y seguimiento de estado de salud.
    """

    def __init__(
        self,
        name: str,
        base_url: str,
        source_type: str = "rss",
        poll_interval_minutes: int = 15,
        requires_auth: bool = False,
        timeout_seconds: int = 30,
        max_retries: int = 3,
        rate_limit_delay: float = 1.0,
    ) -> None:
        self.name = name
        self.base_url = base_url
        self.source_type = source_type
        self.poll_interval_minutes = poll_interval_minutes
        self.requires_auth = requires_auth
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.rate_limit_delay = rate_limit_delay

        # Estado de salud en memoria
        self.status = SourceStatus.OPERATIVA
        self.last_checked_at: datetime | None = None
        self.last_success_at: datetime | None = None
        self.consecutive_errors: int = 0
        self.last_error: str | None = None
        self._last_request_time: float = 0.0

    @abc.abstractmethod
    async def fetch_jobs(
        self,
        session: aiohttp.ClientSession,
        criteria: Any | None = None,
    ) -> list[JobPayload]:
        """Extrae ofertas recientes desde la fuente.

        Debe capturar excepciones internas y retornar una lista de JobPayload normalizados.
        """
        pass

    async def _rate_limit(self) -> None:
        """Aplica pausa de cortesía para respetar los servidores del portal."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    async def request_get(
        self,
        session: aiohttp.ClientSession,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> str:
        """Realiza una petición GET segura con reintentos y backoff exponencial."""
        if not is_safe_url(url):
            raise SourceError(f"URL no permitida por seguridad (SSRF protection): {url}")

        await self._rate_limit()

        default_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36 EmpleoRadarBot/1.0"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
        }
        if headers:
            default_headers.update(headers)

        delay = 1.0
        for attempt in range(1, self.max_retries + 1):
            try:
                timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
                async with session.get(
                    url,
                    headers=default_headers,
                    params=params,
                    timeout=timeout,
                    allow_redirects=True,
                ) as response:
                    if response.status == 200:
                        return await response.text(encoding="utf-8", errors="replace")
                    elif response.status in (429, 503, 504):
                        logger.warning(
                            "[%s] HTTP %d (intento %d/%d). Reintentando en %.1fs...",
                            self.name,
                            response.status,
                            attempt,
                            self.max_retries,
                            delay,
                        )
                        await asyncio.sleep(delay)
                        delay *= 2
                    else:
                        raise SourceError(f"HTTP {response.status} recibido desde {url}")
            except (TimeoutError, aiohttp.ClientError) as err:
                logger.warning(
                    "[%s] Error de conexión (intento %d/%d): %s",
                    self.name,
                    attempt,
                    self.max_retries,
                    err,
                )
                if attempt == self.max_retries:
                    raise SourceError(f"Fallo tras {self.max_retries} intentos: {err}") from err
                await asyncio.sleep(delay)
                delay *= 2

        raise SourceError(f"No se pudo completar la solicitud a {url}")

    def record_success(self, jobs_count: int) -> None:
        """Registra una consulta exitosa."""
        self.last_checked_at = datetime.utcnow()
        self.last_success_at = datetime.utcnow()
        self.consecutive_errors = 0
        self.last_error = None
        self.status = SourceStatus.OPERATIVA
        logger.info("[%s] Extracción exitosa: %d ofertas detectadas.", self.name, jobs_count)

    def record_error(self, error_msg: str) -> None:
        """Registra un fallo en la fuente."""
        self.last_checked_at = datetime.utcnow()
        self.consecutive_errors += 1
        self.last_error = error_msg
        if self.consecutive_errors >= 5:
            self.status = SourceStatus.FALLIDA
        else:
            self.status = SourceStatus.LIMITADA
        logger.error(
            "[%s] Error en fuente (consecutivos=%d): %s",
            self.name,
            self.consecutive_errors,
            error_msg,
        )
