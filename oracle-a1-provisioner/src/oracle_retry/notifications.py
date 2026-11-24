from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone

from .config import Settings

log = logging.getLogger(__name__)


def notify(settings: Settings, title: str, detail: str, *, state: str = "", public_ip: str = "") -> None:
    if not settings.discord_webhook_url:
        return
    description = (f"Instancia: {settings.instance_name}\nRegión: {settings.region}\n"
                  f"Availability Domain: {settings.availability_domain}\n"
                  f"Recursos: {settings.ocpus:g} OCPU / {settings.memory_gbs:g} GB\n"
                  f"Estado: {state or 'N/A'}\nIP pública: {public_ip or 'no asignada'}\n"
                  f"UTC: {datetime.now(timezone.utc).isoformat()}\n{detail}")
    payload = json.dumps({"embeds": [{"title": title[:256], "description": description[:4000]}]}).encode()
    request = urllib.request.Request(settings.discord_webhook_url, data=payload,
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=8):
            pass
    except (urllib.error.URLError, TimeoutError) as exc:
        log.warning("No se pudo enviar notificación Discord: %s", type(exc).__name__)
