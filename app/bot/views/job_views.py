"""Vistas interactivas y botones simplificados para ofertas de empleo."""

from __future__ import annotations

import logging
from typing import Any

import discord
from discord import ui

logger = logging.getLogger(__name__)


class JobCardView(ui.View):
    """Botonera simplificada con enlace directo a la oferta laboral."""

    def __init__(
        self,
        job_url: str | None = None,
        job_id: int | None = None,
        owner_id: int | None = None,
        application_service: Any = None,
        repository: Any = None,
        *,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout)
        # Soportar firmas históricas (job_id, job_url) o directas (job_url=...)
        url = job_url
        jid = job_id
        if isinstance(job_url, int):
            jid = job_url
            url = str(job_id) if job_id else ""

        self.job_url = url or ""
        self.job_id = jid

        # ÚNICAMENTE el botón de tipo URL / Link para ir a la oferta
        if self.job_url and (
            self.job_url.startswith("http://") or self.job_url.startswith("https://")
        ):
            self.add_item(
                ui.Button(
                    label="Ver oferta",
                    style=discord.ButtonStyle.link,
                    url=self.job_url,
                    emoji="🔗",
                )
            )


# Alias de compatibilidad hacia atrás
JobCardLayoutView = JobCardView
