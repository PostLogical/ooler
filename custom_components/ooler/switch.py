"""Support for Ooler Sleep System switches."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OolerConfigEntry
from .models import OolerData


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: OolerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Ooler switches."""
    data: OolerData = config_entry.runtime_data
    entities = [
        OolerCleaningSwitch(data),
        OolerConnectionSwitch(data),
    ]
    async_add_entities(entities)


class OolerCleaningSwitch(SwitchEntity):
    """Representation of Ooler Cleaning switch."""

    _attr_has_entity_name = True

    def __init__(self, data: OolerData) -> None:
        """Initialize the switch entity."""
        self._data = data
        self._attr_name = "Cleaning"
        self._attr_unique_id = f"{data.address}_cleaning_binary_sensor"
        self._attr_device_info = DeviceInfo(
            name=data.model, connections={(dr.CONNECTION_BLUETOOTH, data.address)}
        )

    @property
    def available(self) -> bool:
        """Determine if the entity is available."""
        return self._data.client.is_connected

    @callback
    def _handle_state_update(self, *args: Any) -> None:
        """Handle state update."""
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register callback on add."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._data.client.register_callback(self._handle_state_update)
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if the device is cleaning."""
        if self._data.client.state is not None:
            return self._data.client.state.clean
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start cleaning the unit."""
        await self._data.async_ensure_connected()
        await self._data.client.set_clean(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop cleaning the unit."""
        await self._data.async_ensure_connected()
        await self._data.client.set_clean(False)


class OolerConnectionSwitch(SwitchEntity):
    """Representation of Ooler bluetooth connection switch."""

    _attr_has_entity_name = True

    def __init__(self, data: OolerData) -> None:
        """Initialize the switch entity."""
        self._data = data
        self._attr_name = "Bluetooth Connection"
        self._attr_unique_id = f"{data.address}_connection_binary_sensor"
        self._attr_device_info = DeviceInfo(
            name=data.model, connections={(dr.CONNECTION_BLUETOOTH, data.address)}
        )

    @property
    def available(self) -> bool:
        """This switch controls availability, so always return true."""
        return True

    @callback
    def _handle_state_update(self, *args: Any) -> None:
        """Handle state update."""
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register callback on add."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._data.client.register_callback(self._handle_state_update)
        )

    @property
    def is_on(self) -> bool:
        """Return true if the device is connected."""
        return self._data.client.is_connected

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Connect to the device."""
        self._data.connection_enabled = True
        await self._data.async_ensure_connected()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disconnect from the device and suppress auto-reconnect."""
        self._data.connection_enabled = False
        if self._data.client.is_connected:
            await self._data.client.stop()
