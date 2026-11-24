from __future__ import annotations

import logging
import time
from typing import Any, Callable

import oci
from oci.exceptions import ServiceError
from requests.exceptions import ConnectionError, Timeout

from .config import Settings

log = logging.getLogger(__name__)


def build_clients(settings: Settings) -> tuple[Any, Any, Any, Any]:
    config = {"user": settings.user_ocid, "tenancy": settings.tenancy_ocid,
              "fingerprint": settings.fingerprint, "key_content": settings.private_key,
              "region": settings.region}
    if settings.private_key_passphrase:
        config["pass_phrase"] = settings.private_key_passphrase
    oci.config.validate_config(config)
    return (oci.core.ComputeClient(config, timeout=(10, 30)),
            oci.core.BlockstorageClient(config, timeout=(10, 30)),
            oci.core.VirtualNetworkClient(config, timeout=(10, 30)),
            oci.object_storage.ObjectStorageClient(config, timeout=(10, 30)))


def with_retries(call: Callable[[], Any]) -> Any:
    for attempt in range(3):
        try:
            return call()
        except ServiceError as exc:
            if exc.status != 429 or attempt == 2:
                raise
            delay = min(2 ** attempt * 2, 8)
            log.warning("OCI rate limit (429); reintentando en %s segundos", delay)
            time.sleep(delay)
        except (ConnectionError, Timeout):
            if attempt == 2:
                raise
            time.sleep(min(2 ** attempt, 4))
    raise RuntimeError("Se agotaron los reintentos")
