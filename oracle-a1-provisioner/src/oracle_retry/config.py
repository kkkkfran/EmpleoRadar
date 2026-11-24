from __future__ import annotations

import base64
import os
from dataclasses import dataclass


class ConfigurationError(ValueError):
    pass


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"Falta la variable obligatoria {name}")
    return value


def _key() -> str:
    raw = _required("OCI_PRIVATE_KEY")
    if os.getenv("OCI_PRIVATE_KEY_BASE64", "false").lower() in {"1", "true", "yes"}:
        try:
            return base64.b64decode(raw, validate=True).decode("utf-8")
        except Exception as exc:
            raise ConfigurationError("OCI_PRIVATE_KEY no contiene Base64 válido") from exc
    return raw.replace("\\n", "\n")


@dataclass(frozen=True)
class Settings:
    user_ocid: str
    tenancy_ocid: str
    fingerprint: str
    private_key: str
    private_key_passphrase: str | None
    region: str
    compartment_ocid: str
    availability_domain: str
    subnet_ocid: str
    boot_volume_ocid: str
    ssh_public_key: str
    dry_run: bool
    discord_webhook_url: str | None
    state_bucket: str | None
    object_storage_namespace: str | None
    instance_name: str
    ocpus: float
    memory_gbs: float
    capacity_alerts: bool

    @classmethod
    def from_env(cls) -> "Settings":
        dry_run = os.getenv("DRY_RUN", "true").strip().lower() in {"1", "true", "yes"}
        bucket = os.getenv("OCI_STATE_BUCKET", "").strip() or None
        namespace = os.getenv("OCI_OBJECT_STORAGE_NAMESPACE", "").strip() or None
        if not dry_run and not (bucket and namespace):
            raise ConfigurationError("El modo real requiere OCI_STATE_BUCKET y OCI_OBJECT_STORAGE_NAMESPACE para el bloqueo persistente")
        try:
            ocpus, memory = float(os.getenv("INSTANCE_OCPUS", "1")), float(os.getenv("INSTANCE_MEMORY_GBS", "6"))
        except ValueError as exc:
            raise ConfigurationError("INSTANCE_OCPUS y INSTANCE_MEMORY_GBS deben ser números") from exc
        if ocpus != 1 or memory != 6:
            raise ConfigurationError("Por seguridad, este despliegue solo permite exactamente 1 OCPU y 6 GB RAM")
        for name in ("OCI_USER_OCID", "OCI_TENANCY_OCID", "OCI_FINGERPRINT", "OCI_REGION",
                     "OCI_COMPARTMENT_OCID", "OCI_AVAILABILITY_DOMAIN", "OCI_SUBNET_OCID", "OCI_BOOT_VOLUME_OCID"):
            _required(name)
        key = _key()
        if "BEGIN" not in key or "PRIVATE KEY" not in key:
            raise ConfigurationError("OCI_PRIVATE_KEY no parece ser una clave privada PEM")
        ssh = _required("OCI_SSH_PUBLIC_KEY")
        if not ssh.startswith(("ssh-rsa ", "ssh-ed25519 ", "ecdsa-sha2-")):
            raise ConfigurationError("OCI_SSH_PUBLIC_KEY debe ser una clave pública OpenSSH")
        return cls(
            user_ocid=_required("OCI_USER_OCID"), tenancy_ocid=_required("OCI_TENANCY_OCID"),
            fingerprint=_required("OCI_FINGERPRINT"), private_key=key,
            private_key_passphrase=os.getenv("OCI_PRIVATE_KEY_PASSPHRASE") or None,
            region=_required("OCI_REGION"), compartment_ocid=_required("OCI_COMPARTMENT_OCID"),
            availability_domain=_required("OCI_AVAILABILITY_DOMAIN"), subnet_ocid=_required("OCI_SUBNET_OCID"),
            boot_volume_ocid=_required("OCI_BOOT_VOLUME_OCID"), ssh_public_key=ssh,
            dry_run=dry_run, discord_webhook_url=os.getenv("DISCORD_WEBHOOK_URL") or None,
            state_bucket=bucket, object_storage_namespace=namespace,
            instance_name=os.getenv("INSTANCE_NAME", "servidor-bots"), ocpus=ocpus,
            memory_gbs=memory, capacity_alerts=os.getenv("NOTIFY_CAPACITY", "false").lower() in {"1", "true", "yes"},
        )
