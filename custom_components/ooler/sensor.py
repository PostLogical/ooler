"""Support for Ooler Sleep System sensors."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import PERCENTAGE
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
    """Set up the Ooler sensors."""
    data: OolerData = config_entry.runtime_data
    async_add_entities([OolerWaterLevelSensorEntity(data)])


class OolerSensorEntity(SensorEntity):
    """Representation of an Ooler sensor."""

    _attr_has_entity_name = True

    def __init__(self, data: OolerData) -> None:
        """Initialize the sensor entity."""
        self._data = data
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


class OolerWaterLevelSensorEntity(OolerSensorEntity):
    """Representation of an Ooler water level sensor."""

    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, data: OolerData) -> None:
        """Initialize the water level sensor entity."""
        super().__init__(data)
        self._attr_name = "Water Level"
        self._attr_unique_id = f"{data.address}_water_level_sensor"

    @property
    def native_value(self) -> int | None:
        """Return the water level of the Ooler."""
        return self._data.client.state.water_level
