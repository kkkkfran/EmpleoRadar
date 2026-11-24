from __future__ import annotations

import logging
import uuid
from typing import Any

import oci
from oci.exceptions import ServiceError

from .config import Settings
from .oci_client import with_retries
from .validators import ValidationError, validate_resources

log = logging.getLogger(__name__)
PROJECT_TAG = "oracle-a1-auto-provisioner"
# One idempotency token per launch request; OCI SDK retries within this request reuse it.
RETRY_TOKEN = str(uuid.uuid4())


def _all_pages(method: Any, **kwargs: Any) -> list[Any]:
    result: list[Any] = []
    page = None
    while True:
        response = method(**kwargs, **({"page": page} if page else {}))
        result.extend(response.data)
        page = response.headers.get("opc-next-page")
        if not page:
            return result


class InstanceManager:
    def __init__(self, settings: Settings, compute: Any, block: Any, network: Any, object_storage: Any):
        self.s, self.compute, self.block, self.network, self.storage = settings, compute, block, network, object_storage
        self.running_instance: Any | None = None
        self.public_ip = ""

    def _existing(self) -> list[Any]:
        instances = _all_pages(self.compute.list_instances, compartment_id=self.s.compartment_ocid)
        by_id = {i.id: i for i in instances}
        target = [i for i in instances if i.lifecycle_state != "TERMINATED" and
                  (i.display_name == self.s.instance_name
                   or (i.freeform_tags or {}).get("provisioner") == PROJECT_TAG)]
        attachments = _all_pages(self.compute.list_boot_volume_attachments,
                                  compartment_id=self.s.compartment_ocid,
                                  availability_domain=self.s.availability_domain)
        volume_attached = [a for a in attachments if a.boot_volume_id == self.s.boot_volume_ocid]
        for a in volume_attached:
            instance = by_id.get(a.instance_id)
            if instance and instance not in target:
                target.append(instance)
        if volume_attached and not target:
            raise ValidationError("El volumen está conectado a una instancia no identificada; intervención manual requerida")
        return target

    def _state_lock(self) -> bool:
        """Atomically create durable lock object. A lock is intentionally never auto-released."""
        assert self.s.state_bucket and self.s.object_storage_namespace
        key = f"oracle-a1-auto-provisioner/{self.s.compartment_ocid}/{self.s.boot_volume_ocid}.json"
        body = b'{"state":"launch-requested"}'
        try:
            self.storage.put_object(self.s.object_storage_namespace, self.s.state_bucket, key, body,
                                    if_none_match="*")
            return True
        except ServiceError as exc:
            if exc.status in (409, 412):
                return False
            raise

    def _release_state_lock(self) -> None:
        key = f"oracle-a1-auto-provisioner/{self.s.compartment_ocid}/{self.s.boot_volume_ocid}.json"
        self.storage.delete_object(self.s.object_storage_namespace, self.s.state_bucket, key)

    def run(self) -> str:
        volume = with_retries(lambda: self.block.get_boot_volume(self.s.boot_volume_ocid)).data
        subnet = with_retries(lambda: self.network.get_subnet(self.s.subnet_ocid)).data
        validate_resources(volume, subnet, self.s.compartment_ocid, self.s.availability_domain)
        image_id = getattr(volume, "image_id", None)
        if not image_id:
            raise ValidationError("OCI no informa la imagen de origen del boot volume; no se puede validar compatibilidad con Ampere")
        compatible_shapes = with_retries(lambda: self.compute.list_shapes(
            compartment_id=self.s.compartment_ocid, availability_domain=self.s.availability_domain,
            image_id=image_id, shape="VM.Standard.A1.Flex")).data
        if not any(shape.shape == "VM.Standard.A1.Flex" for shape in compatible_shapes):
            raise ValidationError("OCI no anuncia VM.Standard.A1.Flex como compatible con la imagen de origen del boot volume")
        existing = self._existing()
        if existing:
            states = ", ".join(sorted({i.lifecycle_state for i in existing}))
            log.info("Instancia objetivo existente; no se solicitará otra (estados: %s)", states)
            self.running_instance = next((i for i in existing if i.lifecycle_state == "RUNNING"), None)
            if self.running_instance:
                attachments = _all_pages(self.compute.list_vnic_attachments,
                                         compartment_id=self.s.compartment_ocid,
                                         instance_id=self.running_instance.id)
                if attachments:
                    try:
                        self.public_ip = with_retries(lambda: self.network.get_vnic(attachments[0].vnic_id)).data.public_ip or ""
                    except Exception as exc:
                        log.warning("No se pudo consultar la IP pública (%s)", type(exc).__name__)
                return "running"
            return "existing"
        # OCI boot-volume launch consumes the original volume. Reject all attached states.
        attachments = _all_pages(self.compute.list_boot_volume_attachments,
                                  compartment_id=self.s.compartment_ocid,
                                  availability_domain=self.s.availability_domain)
        if any(a.boot_volume_id == self.s.boot_volume_ocid and a.lifecycle_state != "DETACHED" for a in attachments):
            raise ValidationError("El boot volume ya está conectado; no se intentará lanzar")
        if self.s.dry_run:
            log.info("DRY_RUN: se lanzaría %s desde el boot volume configurado", self.s.instance_name)
            return "dry_run"
        if not self._state_lock():
            log.warning("Ya existe el bloqueo persistente de lanzamiento; no se repetirá la solicitud")
            return "locked"
        details = oci.core.models.LaunchInstanceDetails(
            availability_domain=self.s.availability_domain,
            compartment_id=self.s.compartment_ocid,
            display_name=self.s.instance_name,
            shape="VM.Standard.A1.Flex",
            shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(ocpus=1, memory_in_gbs=6),
            source_details=oci.core.models.InstanceSourceViaBootVolumeDetails(boot_volume_id=self.s.boot_volume_ocid),
            create_vnic_details=oci.core.models.CreateVnicDetails(subnet_id=self.s.subnet_ocid,
                                                                  assign_public_ip=True),
            metadata={"ssh_authorized_keys": self.s.ssh_public_key},
            freeform_tags={"provisioner": PROJECT_TAG, "boot_volume_id": self.s.boot_volume_ocid},
        )
        try:
            response = self.compute.launch_instance(details, opc_retry_token=RETRY_TOKEN)
        except ServiceError as exc:
            if exc.status == 500 and ("capacity" in (exc.message or "").lower()
                                      or "capacity" in (exc.code or "").lower()):
                log.info("Sin capacidad para VM.Standard.A1.Flex; se podrá reintentar en próxima ejecución")
                # The API explicitly rejected the request, so this execution owns a
                # safe-to-release reservation. No instance can have been created.
                self._release_state_lock()
                return "capacity"
            if 400 <= exc.status < 500:
                # A 4xx response is a definite rejection, so a later corrected/retried
                # run may safely make a new request. 5xx and network errors stay locked.
                self._release_state_lock()
            raise
        except Exception:
            # Ambiguous: keep lock and let the next run inspect OCI instead of launching again.
            log.exception("Resultado de lanzamiento ambiguo; bloqueo persistente conservado")
            raise
        log.info("Solicitud OCI aceptada; instance_id=%s", response.data.id)
        return "created"

    def claim_running_notification(self) -> bool:
        """Persist a one-time notification claim so a running instance does not spam Discord."""
        if not self.running_instance or not self.s.state_bucket or not self.s.object_storage_namespace:
            return False
        key = f"oracle-a1-auto-provisioner/{self.s.compartment_ocid}/{self.s.boot_volume_ocid}-running-notified.json"
        try:
            self.storage.put_object(self.s.object_storage_namespace, self.s.state_bucket, key,
                                    b'{"state":"running-notified"}', if_none_match="*")
            return True
        except ServiceError as exc:
            if exc.status in (409, 412):
                return False
            raise
