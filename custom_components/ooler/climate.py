"""Support for Ooler Sleep System controls."""

from __future__ import annotations

from typing import Any, Literal, cast

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OolerConfigEntry
from .const import (
    _LOGGER,
    DEFAULT_MAX_TEMP_C,
    DEFAULT_MAX_TEMP_F,
    DEFAULT_MIN_TEMP_C,
    DEFAULT_MIN_TEMP_F,
)
from .coordinator import OolerCoordinator
from .entity import OolerEntity

PARALLEL_UPDATES = 1
SERVICE_CLEAN = "clean_service"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: OolerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Ooler thermostat."""
    coordinator = config_entry.runtime_data
    async_add_entities([Ooler(coordinator)])
    platform = entity_platform.async_get_current_platform()

    platform.async_register_entity_service(
        SERVICE_CLEAN,
        {},
        "async_set_clean",
    )


class Ooler(OolerEntity, ClimateEntity):
    """Representation of Ooler Thermostat."""

    _attr_name = None
    _attr_target_temperature_step = 1

    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )

    def __init__(self, coordinator: OolerCoordinator) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"ooler_{coordinator.address}_thermostat"
        self._operation_list: list[HVACMode] = [HVACMode.OFF, HVACMode.AUTO]
        self._fan_modes: list[str] = ["Silent", "Regular", "Boost"]

    @property
    def temperature_unit(self) -> str:
        """Return temperature unit based on device setting."""
        if self.coordinator.client.state.temperature_unit == "C":
            return UnitOfTemperature.CELSIUS
        return UnitOfTemperature.FAHRENHEIT

    @property
    def min_temp(self) -> float:
        """Return the minimum target temperature."""
        if self.coordinator.client.state.temperature_unit == "C":
            return DEFAULT_MIN_TEMP_C
        return DEFAULT_MIN_TEMP_F

    @property
    def max_temp(self) -> float:
        """Return the maximum target temperature."""
        if self.coordinator.client.state.temperature_unit == "C":
            return DEFAULT_MAX_TEMP_C
        return DEFAULT_MAX_TEMP_F

    @property
    def target_temperature(self) -> int | None:
        """Return the temperature we try to reach."""
        return self.coordinator.client.state.set_temperature

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self.coordinator.client.state.actual_temperature

    @property
    def fan_mode(self) -> str | None:
        """Return the fan setting."""
        return self.coordinator.client.state.mode

    @property
    def fan_modes(self) -> list[str] | None:
        """Return the fan modes list."""
        return self._fan_modes

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return current operation."""
        if self.coordinator.client.state.power:
            return HVACMode.AUTO
        return HVACMode.OFF

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return the operation modes list."""
        return self._operation_list

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current HVAC action (heating, cooling)."""
        hvacmode = self.hvac_mode
        if hvacmode == HVACMode.OFF:
            return HVACAction.OFF
        settemp = self.target_temperature
        currenttemp = self.current_temperature
        if currenttemp is not None and settemp is not None:
            if currenttemp > settemp:
                return HVACAction.COOLING
            if currenttemp < settemp:
                return HVACAction.HEATING
        return HVACAction.IDLE

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return the list of supported features."""
        return self._attr_supported_features

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return sleep schedule details as extra state attributes."""
        schedule = self.coordinator.client.sleep_schedule
        if schedule is None or not schedule.nights:
            return None
        day_names = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        nights = []
        for night in schedule.nights:
            night_dict: dict[str, Any] = {
                "day": day_names[night.day],
                "bedtime": night.temps[0][0].strftime("%H:%M") if night.temps else None,
                "off_time": night.off_time.strftime("%H:%M"),
                "temps": [
                    {"time": t.strftime("%H:%M"), "temp_f": temp}
                    for t, temp in night.temps
                ],
            }
            if night.warm_wake is not None:
                night_dict["warm_wake"] = {
                    "target_temp_f": night.warm_wake.target_temp_f,
                    "duration_min": night.warm_wake.duration_min,
                }
            nights.append(night_dict)
        return {
            "sleep_schedule_days": [day_names[n.day] for n in schedule.nights],
            "sleep_schedule_nights": nights,
        }

    @property
    def cleaning(self) -> bool | None:
        """Return if the unit is cleaning itself."""
        return self.coordinator.client.state.clean

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVACMode (On/Off)."""
        await self.coordinator.async_ensure_connected()
        power = hvac_mode != HVACMode.OFF
        await self.coordinator.client.set_power(power)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan mode. Valid values are Silent, Regular, and Boost."""
        if fan_mode not in self._fan_modes:
            _LOGGER.error(
                "Invalid fan_mode value: Valid values are 'Silent', 'Regular', 'Boost'"
            )
            return
        await self.coordinator.async_ensure_connected()
        await self.coordinator.client.set_mode(
            cast("Literal['Silent', 'Regular', 'Boost']", fan_mode)
        )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            raise ValueError("No target temperature provided.")
        if temp == self.target_temperature:
            return
        await self.coordinator.async_ensure_connected()
        await self.coordinator.client.set_temperature(int(temp))

    async def async_set_clean(self) -> None:
        """Start cleaning the unit."""
        await self.coordinator.async_ensure_connected()
        await self.coordinator.client.set_clean(True)
