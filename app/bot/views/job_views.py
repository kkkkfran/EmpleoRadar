"""Tarjetas interactivas de ofertas usando Discord Components V2."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import discord
from discord import ui

from app.database.models import Job
from app.jobs.models import JobMatchResult, JobPayload

PENDING = "pending"
APPLIED = "applied"
DISMISSED = "dismissed"
STATE_COLOURS = {
    PENDING: discord.Color.from_rgb(0, 176, 244),
    APPLIED: discord.Color.from_rgb(241, 196, 15),
    DISMISSED: discord.Color.from_rgb(231, 76, 60),
}


def _value(value: Any, fallback: str = "No informado") -> str:
    if value is None or value == "":
        return fallback
    return str(getattr(value, "value", value)).replace("_", " ").capitalize()


def _layout(job: JobPayload | Job, job_id: int, score: int, decision: str) -> ui.LayoutView:
    title = (job.title or "Oferta laboral")[:240]
    company = job.company or "Empresa confidencial"
    location = ", ".join(x for x in (job.comuna, job.region) if x) or getattr(
        job, "location_raw", None
    ) or getattr(job, "location", None) or "Chile"
    description = " ".join((job.description or "").split())[:2200]
    status = {
        APPLIED: "🟡 **Estado: Ya postulé**",
        DISMISSED: "🔴 **Estado: No me interesa**",
        PENDING: "🔵 **Estado: Pendiente de revisar**",
    }.get(decision, "🔵 **Estado: Pendiente de revisar**")
    details = [
        f"**Modalidad:** {_value(job.modality)}",
        f"**Contrato:** {_value(job.contract_type)}",
        f"**Jornada:** {_value(getattr(job, 'schedule', None))}",
    ]
    salary_min, salary_max = job.salary_min, job.salary_max
    if salary_min or salary_max:
        if salary_min and salary_max and salary_min != salary_max:
            salary = f"${salary_min:,.0f} – ${salary_max:,.0f}".replace(",", ".")
        else:
            salary = f"${(salary_max or salary_min):,.0f}".replace(",", ".")
        details.append(f"**Renta:** {salary} CLP")
    source = getattr(job, "source_name", None)
    if not source:
        try:
            source = job.source.name if job.source else None
        except Exception:
            source = None
    published = job.published_at or getattr(job, "detected_at", None) or datetime.now()

    container = ui.Container(accent_color=STATE_COLOURS.get(decision, STATE_COLOURS[PENDING]))
    container.add_item(ui.TextDisplay(f"### 💼 {title}\n**{company}** · 📍 {location}"))
    container.add_item(ui.Separator())
    container.add_item(ui.TextDisplay("\n".join(details)))
    container.add_item(ui.TextDisplay(f"🎯 **Compatibilidad: {score}/100**\n{status}"))
    requirements = " ".join((getattr(job, "requirements", None) or "").split())[:700]
    experience = getattr(job, "experience_required", None)
    education = getattr(job, "education_required", None)
    if experience or education:
        container.add_item(ui.Separator())
        qualifications = []
        if experience:
            qualifications.append(f"**Experiencia:** {experience}")
        if education:
            qualifications.append(f"**Formación:** {education}")
        container.add_item(ui.TextDisplay("\n".join(qualifications)))
    if requirements:
        container.add_item(ui.Separator())
        container.add_item(ui.TextDisplay(f"**Requisitos**\n{requirements}"))
    if description:
        container.add_item(ui.Separator())
        chunks = [description[i : i + 700] for i in range(0, len(description), 700)]
        for index, chunk in enumerate(chunks):
            heading = "**Descripción completa**\n" if index == 0 else ""
            container.add_item(ui.TextDisplay(f"{heading}{chunk}"))
    container.add_item(ui.Separator())
    container.add_item(ui.TextDisplay(
        f"-# Fuente: {source or 'Fuente externa'} · ID #{job_id} · "
        f"{published:%d-%m-%Y %H:%M} · EmpleoRadar"
    ))
    row = ui.ActionRow()
    if job.url and job.url.startswith(("http://", "https://")):
        row.add_item(ui.Button(label="Ver oferta", style=discord.ButtonStyle.link, url=job.url))
    row.add_item(ui.Button(
        label="Ya postulé" if decision != APPLIED else "Postulación marcada",
        style=discord.ButtonStyle.success,
        custom_id=f"job:applied:{job_id}:{score}",
        disabled=decision == APPLIED,
    ))
    row.add_item(ui.Button(
        label="No me interesa" if decision != DISMISSED else "Descartada",
        style=discord.ButtonStyle.danger,
        custom_id=f"job:dismissed:{job_id}:{score}",
        disabled=decision == DISMISSED,
    ))
    container.add_item(row)
    view = ui.LayoutView(timeout=None)
    view.add_item(container)
    return view


async def _change_decision(
    interaction: discord.Interaction, job_id: int, score: int, decision: str
) -> None:
    bot = interaction.client
    if interaction.user.id != bot.owner_id:
        await interaction.response.send_message("Este control pertenece al dueño del bot.", ephemeral=True)
        return
    job = await bot.repo.get_job(job_id)
    if not job:
        await interaction.response.send_message("La oferta ya no está disponible.", ephemeral=True)
        return
    await bot.repo.set_job_decision(job_id, decision)
    await interaction.response.edit_message(view=_layout(job, job_id, score, decision))


class AppliedButton(
    ui.DynamicItem[ui.Button], template=r"job:applied:(?P<job_id>\d+):(?P<score>\d+)"
):
    def __init__(self, job_id: int, score: int) -> None:
        super().__init__(ui.Button(label="Ya postulé", custom_id=f"job:applied:{job_id}:{score}"))
        self.job_id = job_id
        self.score = score

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        return cls(int(match["job_id"]), int(match["score"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await _change_decision(interaction, self.job_id, self.score, APPLIED)


class DismissedButton(
    ui.DynamicItem[ui.Button], template=r"job:dismissed:(?P<job_id>\d+):(?P<score>\d+)"
):
    def __init__(self, job_id: int, score: int) -> None:
        super().__init__(
            ui.Button(label="No me interesa", custom_id=f"job:dismissed:{job_id}:{score}")
        )
        self.job_id = job_id
        self.score = score

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        return cls(int(match["job_id"]), int(match["score"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await _change_decision(interaction, self.job_id, self.score, DISMISSED)


def create_job_card_layout(
    job: JobPayload | Job,
    match_result: JobMatchResult | None = None,
    job_id: int | None = None,
    decision: str = PENDING,
) -> ui.LayoutView:
    """Construye una tarjeta Components V2 legible y persistente."""
    return _layout(job, job_id or 0, match_result.score if match_result else 50, decision)


# Compatibilidad con imports históricos.
JobCardView = ui.LayoutView
JobCardLayoutView = ui.LayoutView
