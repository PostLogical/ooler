"""Support for Ooler Sleep System sensors."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OolerConfigEntry
from .coordinator import OolerCoordinator
from .entity import OolerEntity

PARALLEL_UPDATES = 0

_DAY_NAMES = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: OolerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Ooler sensors."""
    coordinator = config_entry.runtime_data
    async_add_entities(
        [
            OolerWaterLevelSensor(coordinator),
            OolerScheduleTonightSensor(coordinator),
        ]
    )


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


class OolerScheduleTonightSensor(OolerEntity, SensorEntity):
    """Sensor showing tonight's sleep schedule at a glance."""

    _attr_translation_key = "schedule_tonight"

    def __init__(self, coordinator: OolerCoordinator) -> None:
        """Initialize the schedule tonight sensor entity."""
        super().__init__(coordinator)
        self._attr_name = "Schedule Tonight"
        self._attr_unique_id = f"{coordinator.address}_schedule_tonight"

    @property
    def native_value(self) -> str | None:
        """Return a summary of tonight's schedule."""
        night = self.coordinator.tonight_schedule
        if night is None or not night.temps:
            return None
        bedtime = night.temps[0][0].strftime("%I:%M %p").lstrip("0")
        off = night.off_time.strftime("%I:%M %p").lstrip("0")
        temp = night.temps[0][1]
        return f"{bedtime}-{off}, {temp}\u00b0F"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return tonight's schedule details."""
        night = self.coordinator.tonight_schedule
        if night is None:
            return None
        attrs: dict[str, Any] = {
            "day": _DAY_NAMES[night.day],
            "bedtime": night.temps[0][0].strftime("%H:%M") if night.temps else None,
            "off_time": night.off_time.strftime("%H:%M"),
            "temps": [
                {"time": t.strftime("%H:%M"), "temp_f": temp} for t, temp in night.temps
            ],
        }
        if night.warm_wake is not None:
            attrs["warm_wake"] = {
                "target_temp_f": night.warm_wake.target_temp_f,
                "duration_min": night.warm_wake.duration_min,
            }
        return attrs
