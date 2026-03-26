"""Support for Ooler Sleep System sensors."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OolerConfigEntry
from .coordinator import OolerCoordinator
from .entity import OolerEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: OolerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Ooler sensors."""
    coordinator = config_entry.runtime_data
    async_add_entities([OolerWaterLevelSensor(coordinator)])


class OolerWaterLevelSensor(OolerEntity, SensorEntity):
    """Representation of an Ooler water level sensor."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_translation_key = "water_level"

    def __init__(self, coordinator: OolerCoordinator) -> None:
        """Initialize the water level sensor entity."""
        super().__init__(coordinator)
        self._attr_name = "Water Level"
        self._attr_unique_id = f"{coordinator.address}_water_level_sensor"

    @property
    def native_value(self) -> int | None:
        """Return the water level of the Ooler."""
        return self.coordinator.client.state.water_level
