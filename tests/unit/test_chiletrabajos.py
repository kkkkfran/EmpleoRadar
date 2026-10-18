"""Pruebas unitarias para el conector de ChileTrabajos y fechas."""

from __future__ import annotations

from datetime import datetime

from app.sources.chiletrabajos import ChileTrabajosSource, parse_chiletrabajos_date


def test_parse_chiletrabajos_date() -> None:
    dt1 = parse_chiletrabajos_date("15 de Octubre de 2026")
    assert dt1 is not None
    assert dt1.year == 2026
    assert dt1.month == 10
    assert dt1.day == 15

    dt2 = parse_chiletrabajos_date("Hoy")
    assert dt2 is not None
    assert dt2.day == datetime.now().day

    dt3 = parse_chiletrabajos_date("Ayer")
    assert dt3 is not None

    dt4 = parse_chiletrabajos_date("Texto sin fecha")
    assert dt4 is None


def test_parse_html_job_items() -> None:
    sample_html = """
    <div class="job-item">
      <h2><a href="https://www.chiletrabajos.cl/trabajo/ingeniero-en-informatica-3914560">Ingeniero en Informática</a></h2>
      <h3 class="meta">Empresa Tech, Concepción</h3>
      <h3 class="meta"><i class="far fa-calendar"></i> 15 de Octubre de 2026</h3>
      <p class="description">Desarrollo de software con Python y microservicios.</p>
      <a class="guardar" data-id="3914560"></a>
    </div>
    <div class="job-item">
      <h2><a href="/trabajo/soporte-chillan-3914561">Soporte TI Chillán</a></h2>
      <h3 class="meta">Chillán TI, Chillán</h3>
      <h3 class="meta"><i class="far fa-calendar"></i> 14 de Octubre de 2026</h3>
      <p class="description">Soporte computacional y redes.</p>
    </div>
    """
    source = ChileTrabajosSource()
    jobs = source._parse_html_job_items(sample_html)

    assert len(jobs) == 2
    # Job 1 - Concepción (Biobío)
    job1 = jobs[0]
    assert job1.title == "Ingeniero en Informática"
    assert job1.company == "Empresa Tech"
    assert job1.comuna == "Concepción"
    assert job1.region == "Biobío"
    assert job1.external_id == "3914560"
    assert job1.published_at == datetime(2026, 10, 15, 12, 0, 0)

    # Job 2 - Chillán (Ñuble)
    job2 = jobs[1]
    assert job2.title == "Soporte TI Chillán"
    assert job2.comuna == "Chillán"
    assert job2.region == "Ñuble"
    assert job2.external_id == "3914561"
    assert job2.published_at == datetime(2026, 10, 14, 12, 0, 0)

