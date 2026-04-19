"""Base entity for the Ooler Sleep System integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .coordinator import OolerCoordinator


class OolerEntity(Entity):
    """Base class for Ooler entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: OolerCoordinator) -> None:
        """Initialize the entity."""
        self.coordinator = coordinator
        self._attr_device_info = DeviceInfo(
            name=coordinator.model,
            connections={(dr.CONNECTION_BLUETOOTH, coordinator.address)},
        )

    @property
    def available(self) -> bool:
        """Return whether the entity is available."""
        return self.coordinator.is_connected

    @callback
    def _handle_state_update(self, *_args: Any) -> None:
        """Handle coordinator state update."""
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register state update callback."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_state_update)
        )
