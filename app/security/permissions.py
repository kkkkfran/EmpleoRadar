"""Control de permisos y acceso para EmpleoRadar."""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable, Coroutine
from typing import Any

import discord

logger = logging.getLogger(__name__)


def owner_only() -> Callable:
    """Decorador que restringe un comando al propietario del bot."""

    def decorator(
        func: Callable[..., Coroutine[Any, Any, Any]],
    ) -> Callable[..., Coroutine[Any, Any, Any]]:
        @functools.wraps(func)
        async def wrapper(
            self: Any, interaction: discord.Interaction, *args: Any, **kwargs: Any
        ) -> Any:
            owner_id = interaction.client.owner_id  # type: ignore[attr-defined]
            if interaction.user.id != owner_id:
                logger.warning(
                    "Acceso denegado: usuario %s intentó usar comando restringido",
                    interaction.user.id,
                )
                await interaction.response.send_message(
                    "⛔ No tienes permiso para usar este comando.",
                    ephemeral=True,
                )
                return
            return await func(self, interaction, *args, **kwargs)

        return wrapper

    return decorator


def is_owner(interaction: discord.Interaction) -> bool:
    """Verifica si el usuario es el propietario del bot."""
    owner_id = getattr(interaction.client, "owner_id", None)
    return interaction.user.id == owner_id


async def owner_check(interaction: discord.Interaction) -> bool:
    """Check para app_commands que verifica permisos de propietario."""
    if not is_owner(interaction):
        await interaction.response.send_message(
            "⛔ No tienes permiso para usar este comando.",
            ephemeral=True,
        )
        return False
    return True
