from __future__ import annotations

import logging
import sys

from oci.exceptions import ServiceError

from .config import ConfigurationError, Settings
from .instance_manager import InstanceManager
from .logging_config import configure_logging
from .notifications import notify
from .oci_client import build_clients
from .validators import ValidationError

log = logging.getLogger(__name__)


def main() -> int:
    configure_logging()
    settings = None
    try:
        settings = Settings.from_env()
        clients = build_clients(settings)
        manager = InstanceManager(settings, *clients)
        result = manager.run()
        if result == "created":
            notify(settings, "Solicitud OCI aceptada", "La instancia fue solicitada desde el volumen de arranque original.", state="PROVISIONING")
        elif result == "running" and manager.claim_running_notification():
            notify(settings, "Instancia disponible", "La instancia está en estado RUNNING.", state="RUNNING", public_ip=manager.public_ip)
        elif result == "capacity" and settings.capacity_alerts:
            notify(settings, "OCI sin capacidad", "No había capacidad disponible; el bloqueo se conserva para evitar duplicados.", state="CAPACITY_UNAVAILABLE")
        return 0
    except ConfigurationError as exc:
        log.error("Configuración inválida: %s", exc)
        if settings: notify(settings, "Error de configuración", str(exc))
    except ValidationError as exc:
        log.error("Validación detenida: %s", exc)
        if settings: notify(settings, "Intervención manual requerida", str(exc))
    except ServiceError as exc:
        category = "autenticación/permisos" if exc.status in (401, 403) else "error OCI"
        log.error("Error %s de OCI (HTTP %s, código %s)", category, exc.status, exc.code)
        if settings and exc.status in (401, 403): notify(settings, "Error de autenticación o permisos OCI", f"HTTP {exc.status}; código {exc.code}")
    except Exception as exc:
        log.error("Error no recuperable: %s", type(exc).__name__, exc_info=True)
        if settings: notify(settings, "Error crítico del provisionador", f"Error: {type(exc).__name__}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
