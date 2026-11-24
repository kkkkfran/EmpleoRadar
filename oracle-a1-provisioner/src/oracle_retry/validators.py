from __future__ import annotations

from typing import Any


class ValidationError(RuntimeError):
    pass


def validate_resources(volume: Any, subnet: Any, compartment_id: str, availability_domain: str) -> None:
    if volume is None:
        raise ValidationError("El boot volume configurado no existe o no es accesible")
    if getattr(volume, "lifecycle_state", None) != "AVAILABLE":
        raise ValidationError(f"El boot volume debe estar AVAILABLE; estado actual: {getattr(volume, 'lifecycle_state', 'desconocido')}")
    if getattr(volume, "availability_domain", None) != availability_domain:
        raise ValidationError("El boot volume no pertenece al Availability Domain configurado")
    if getattr(volume, "compartment_id", None) != compartment_id:
        raise ValidationError("El boot volume no pertenece al compartimento configurado")
    if subnet is None or getattr(subnet, "lifecycle_state", None) != "AVAILABLE":
        raise ValidationError("La subred no existe, no es accesible o no está AVAILABLE")
    if getattr(subnet, "compartment_id", None) != compartment_id:
        raise ValidationError("La subred no pertenece al compartimento configurado")
    if getattr(subnet, "availability_domain", None) not in (None, availability_domain):
        raise ValidationError("La subred es de otro Availability Domain")
