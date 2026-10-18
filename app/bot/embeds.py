"""Generador de tarjetas y mensajes enriquecidos (Embeds) para Discord en español."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import discord

from app.database.models import Job, Resume
from app.jobs.models import JobMatchResult, JobPayload


def create_job_card_embed(
    job: JobPayload | Job,
    match_result: JobMatchResult | None = None,
    job_id: int | None = None,
) -> discord.Embed:
    """Genera la tarjeta visual completa de una oferta de empleo para Discord."""
    # Color según compatibilidad
    score = match_result.score if match_result else 50
    if score >= 80:
        color = discord.Color.green()
    elif score >= 50:
        color = discord.Color.blue()
    else:
        color = discord.Color.orange()

    title = job.title[:250]
    company = job.company or "Empresa Confidencial"

    embed = discord.Embed(
        title=f"💼 {title}",
        url=job.url,
        description=f"**Empresa:** {company}",
        color=color,
        timestamp=job.published_at or getattr(job, "detected_at", datetime.utcnow()),
    )

    # Ubicación
    loc_parts = []
    if job.comuna:
        loc_parts.append(job.comuna)
    if job.region:
        loc_parts.append(job.region)
    location_str = (
        ", ".join(loc_parts)
        if loc_parts
        else (getattr(job, "location_raw", None) or getattr(job, "location", None) or "Chile")
    )
    embed.add_field(name="📍 Ubicación", value=location_str, inline=True)

    # Modalidad y Contrato
    modality_val = job.modality.value if hasattr(job.modality, "value") else str(job.modality)
    contract_val = (
        job.contract_type.value if hasattr(job.contract_type, "value") else str(job.contract_type)
    )
    embed.add_field(name="🏢 Modalidad", value=modality_val.capitalize(), inline=True)
    embed.add_field(
        name="📄 Contrato", value=contract_val.replace("_", " ").capitalize(), inline=True
    )

    # Sueldo
    if job.salary_min or job.salary_max:
        if job.salary_min and job.salary_max and job.salary_min != job.salary_max:
            sal_str = f"${job.salary_min:,} - ${job.salary_max:,} CLP"
        else:
            sal_val = job.salary_max or job.salary_min
            sal_str = f"${sal_val:,} CLP"
        if getattr(job, "salary_type", None):
            sal_str += f" ({job.salary_type})"
    else:
        sal_str = "No publicado (A convenir)"
    embed.add_field(name="💰 Remuneración", value=sal_str, inline=True)

    # Experiencia
    exp_str = job.experience_required or "No especificada"
    embed.add_field(name="⏳ Experiencia", value=exp_str, inline=True)

    # Compatibilidad
    if match_result:
        reasons_text = "\n".join(f"• {r}" for r in match_result.match_reasons[:3])
        if not reasons_text:
            reasons_text = "Evaluada según perfil y ubicación."
        embed.add_field(
            name=f"🎯 Compatibilidad: {match_result.score}/100",
            value=reasons_text,
            inline=False,
        )

    # Fuente y verificación
    source_name = getattr(job, "source_name", None) or (
        job.source.name if hasattr(job, "source") and job.source else "Fuente externa"
    )
    job_id_str = f" | ID #{job_id}" if job_id else ""
    embed.set_footer(text=f"Fuente: {source_name}{job_id_str} • EmpleoRadar")

    return embed


def create_profile_embed(
    owner_name: str,
    profile_data: dict[str, Any],
    resumes: list[Resume],
) -> discord.Embed:
    """Genera el Embed informativo del perfil profesional del usuario."""
    embed = discord.Embed(
        title=f"👤 Perfil Profesional: {owner_name}",
        description="Datos y preferencias laborales registrados para postulaciones.",
        color=discord.Color.brand_green(),
    )

    edu = profile_data.get("education") or "No registrado"
    embed.add_field(name="🎓 Formación Académica", value=edu, inline=False)

    exp = profile_data.get("availability") or "Inmediata"
    embed.add_field(name="⏱️ Disponibilidad", value=exp, inline=True)

    salary = profile_data.get("salary_expectation_min")
    salary_str = f"${salary:,} CLP líquidos" if salary else "No configurado"
    embed.add_field(name="💵 Renta Esperada", value=salary_str, inline=True)

    excel = profile_data.get("excel_level") or "No configurado"
    license_b = profile_data.get("drivers_license") or "No"
    transport = "Sí" if profile_data.get("own_transport") else "No"
    embed.add_field(
        name="🛠️ Otros antecedentes",
        value=f"• Excel: {excel}\n• Licencia: {license_b}\n• Vehículo propio: {transport}",
        inline=False,
    )

    # Currículums cargados
    if resumes:
        cv_lines = []
        for cv in resumes:
            default_mark = " ⭐ (Predeterminado)" if cv.is_default else ""
            cv_lines.append(
                f"• **{cv.original_filename}** ({cv.label}){default_mark} - {cv.file_size // 1024} KB"
            )
        embed.add_field(
            name=f"📂 Currículums ({len(resumes)})", value="\n".join(cv_lines), inline=False
        )
    else:
        embed.add_field(
            name="📂 Currículums",
            value="No has subido ningún CV aún. Usa `/empleo cv` para cargar uno.",
            inline=False,
        )

    return embed


def create_health_embed(health_data: dict[str, Any]) -> discord.Embed:
    """Genera el Embed con el estado de salud y métricas del sistema."""
    is_ok = health_data.get("status") == "operativo"
    color = discord.Color.green() if is_ok else discord.Color.orange()

    embed = discord.Embed(
        title="🩺 Diagnóstico y Salud de EmpleoRadar",
        color=color,
        timestamp=datetime.utcnow(),
    )

    uptime_mins = health_data.get("uptime_seconds", 0) // 60
    embed.add_field(
        name="⚙️ Estado General",
        value=f"**{health_data.get('status', 'desconocido').upper()}**",
        inline=True,
    )
    embed.add_field(name="⏱️ Uptime", value=f"{uptime_mins} minutos", inline=True)

    stats = health_data.get("job_stats", {})
    embed.add_field(
        name="📊 Métricas de Ofertas",
        value=f"• Total detectadas: **{stats.get('total', 0)}**\n• Notificadas: **{stats.get('notified', 0)}**",
        inline=False,
    )

    # Estado de las fuentes
    sources = health_data.get("sources", [])
    if sources:
        src_lines = []
        for s in sources:
            st = s.get("status", "desconocido")
            icon = "🟢" if st == "operativa" else ("🟡" if st == "limitada" else "🔴")
            err_info = f" ({s.get('last_error')})" if s.get("last_error") else ""
            src_lines.append(f"{icon} **{s.get('name')}**: `{st}`{err_info}")
        embed.add_field(name="🌐 Fuentes Laborales", value="\n".join(src_lines), inline=False)

    return embed
