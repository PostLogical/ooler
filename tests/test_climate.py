"""Tests for the Ooler climate entity."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.climate import HVACAction, HVACMode
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.ooler.climate import Ooler, async_setup_entry
from custom_components.ooler.coordinator import OolerCoordinator

from .conftest import OOLER_ADDRESS, OOLER_NAME, make_mock_client


def make_coordinator_with_client(
    client: MagicMock,
) -> OolerCoordinator:
    """Create a coordinator with a mocked client."""
    coordinator = MagicMock(spec=OolerCoordinator)
    coordinator.address = OOLER_ADDRESS
    coordinator.model = OOLER_NAME
    coordinator.client = client
    coordinator.is_connected = client.is_connected
    return coordinator


async def test_async_setup_entry() -> None:
    """Test platform setup creates entity."""
    hass = MagicMock(spec=HomeAssistant)
    coordinator = MagicMock(spec=OolerCoordinator)
    coordinator.address = OOLER_ADDRESS
    coordinator.model = OOLER_NAME
    coordinator.client = make_mock_client()

    entry = MagicMock()
    entry.runtime_data = coordinator

    added_entities: list = []

    def mock_add_entities(entities: list) -> None:
        added_entities.extend(entities)

    with patch(
        "custom_components.ooler.climate.entity_platform.async_get_current_platform"
    ) as mock_platform:
        mock_platform.return_value = MagicMock()
        await async_setup_entry(hass, entry, mock_add_entities)

    assert len(added_entities) == 1
    assert isinstance(added_entities[0], Ooler)


class TestOolerClimate:
    """Tests for the Ooler climate entity."""

    def _make_entity(
        self, *, connected: bool = True, power: bool = True
    ) -> Ooler:
        client = make_mock_client(connected=connected)
        client.state.power = power
        coordinator = make_coordinator_with_client(client)
        return Ooler(coordinator)

    def test_unique_id(self) -> None:
        """Test unique ID format."""
        entity = self._make_entity()
        assert entity.unique_id == f"ooler_{OOLER_ADDRESS}_thermostat"

    def test_available(self) -> None:
        """Test availability reflects connection state."""
        entity = self._make_entity(connected=True)
        assert entity.available is True

        entity = self._make_entity(connected=False)
        assert entity.available is False

    def test_temperature_unit_fahrenheit(self) -> None:
        """Test temperature unit when device is set to F."""
        entity = self._make_entity()
        entity.coordinator.client.state.temperature_unit = "F"
        assert entity.temperature_unit == UnitOfTemperature.FAHRENHEIT

    def test_temperature_unit_celsius(self) -> None:
        """Test temperature unit when device is set to C."""
        entity = self._make_entity()
        entity.coordinator.client.state.temperature_unit = "C"
        assert entity.temperature_unit == UnitOfTemperature.CELSIUS

    def test_min_max_temp_fahrenheit(self) -> None:
        """Test min/max temp in Fahrenheit."""
        entity = self._make_entity()
        entity.coordinator.client.state.temperature_unit = "F"
        assert entity.min_temp == 54
        assert entity.max_temp == 116

    def test_min_max_temp_celsius(self) -> None:
        """Test min/max temp in Celsius."""
        entity = self._make_entity()
        entity.coordinator.client.state.temperature_unit = "C"
        assert entity.min_temp == 12
        assert entity.max_temp == 47

    def test_target_temperature(self) -> None:
        """Test target temperature returns set_temperature."""
        entity = self._make_entity()
        assert entity.target_temperature == 72

    def test_current_temperature(self) -> None:
        """Test current temperature returns actual_temperature."""
        entity = self._make_entity()
        assert entity.current_temperature == 74

    def test_fan_mode(self) -> None:
        """Test fan mode returns current mode."""
        entity = self._make_entity()
        assert entity.fan_mode == "Regular"

    def test_fan_modes(self) -> None:
        """Test fan modes list."""
        entity = self._make_entity()
        assert entity.fan_modes == ["Silent", "Regular", "Boost"]

    def test_hvac_mode_on(self) -> None:
        """Test HVAC mode when power is on."""
        entity = self._make_entity(power=True)
        assert entity.hvac_mode == HVACMode.AUTO

    def test_hvac_mode_off(self) -> None:
        """Test HVAC mode when power is off."""
        entity = self._make_entity(power=False)
        assert entity.hvac_mode == HVACMode.OFF

    def test_hvac_modes(self) -> None:
        """Test HVAC modes list."""
        entity = self._make_entity()
        assert HVACMode.OFF in entity.hvac_modes
        assert HVACMode.AUTO in entity.hvac_modes

    def test_supported_features(self) -> None:
        """Test supported features."""
        from homeassistant.components.climate import ClimateEntityFeature

        entity = self._make_entity()
        features = entity.supported_features
        assert features & ClimateEntityFeature.TARGET_TEMPERATURE
        assert features & ClimateEntityFeature.FAN_MODE

    def test_hvac_action_off(self) -> None:
        """Test HVAC action is OFF when power is off."""
        entity = self._make_entity(power=False)
        assert entity.hvac_action == HVACAction.OFF

    def test_hvac_action_cooling(self) -> None:
        """Test HVAC action is COOLING when current > target."""
        entity = self._make_entity()
        entity.coordinator.client.state.actual_temperature = 80
        entity.coordinator.client.state.set_temperature = 72
        assert entity.hvac_action == HVACAction.COOLING

    def test_hvac_action_heating(self) -> None:
        """Test HVAC action is HEATING when current < target."""
        entity = self._make_entity()
        entity.coordinator.client.state.actual_temperature = 68
        entity.coordinator.client.state.set_temperature = 72
        assert entity.hvac_action == HVACAction.HEATING

    def test_hvac_action_idle(self) -> None:
        """Test HVAC action is IDLE when at target."""
        entity = self._make_entity()
        entity.coordinator.client.state.actual_temperature = 72
        entity.coordinator.client.state.set_temperature = 72
        assert entity.hvac_action == HVACAction.IDLE

    def test_cleaning(self) -> None:
        """Test cleaning property."""
        entity = self._make_entity()
        entity.coordinator.client.state.clean = True
        assert entity.cleaning is True

    async def test_set_hvac_mode(self) -> None:
        """Test setting HVAC mode calls set_power."""
        entity = self._make_entity()
        await entity.async_set_hvac_mode(HVACMode.AUTO)
        entity.coordinator.client.set_power.assert_called_once_with(True)

        entity = self._make_entity()
        await entity.async_set_hvac_mode(HVACMode.OFF)
        entity.coordinator.client.set_power.assert_called_once_with(False)

    async def test_set_fan_mode(self) -> None:
        """Test setting fan mode."""
        entity = self._make_entity()
        await entity.async_set_fan_mode("Silent")
        entity.coordinator.client.set_mode.assert_called_once_with("Silent")

    async def test_set_fan_mode_invalid(self) -> None:
        """Test setting invalid fan mode does nothing."""
        entity = self._make_entity()
        await entity.async_set_fan_mode("Turbo")
        entity.coordinator.client.set_mode.assert_not_called()

    async def test_set_temperature(self) -> None:
        """Test setting temperature."""
        entity = self._make_entity()
        await entity.async_set_temperature(temperature=68)
        entity.coordinator.client.set_temperature.assert_called_once_with(68)

    async def test_set_temperature_same_value(self) -> None:
        """Test setting same temperature is a no-op."""
        entity = self._make_entity()
        entity.coordinator.client.state.set_temperature = 72
        await entity.async_set_temperature(temperature=72)
        entity.coordinator.client.set_temperature.assert_not_called()

    async def test_set_temperature_no_value(self) -> None:
        """Test setting temperature without value raises."""
        entity = self._make_entity()
        with pytest.raises(ValueError, match="No target temperature"):
            await entity.async_set_temperature()

    async def test_set_clean(self) -> None:
        """Test starting clean cycle."""
        entity = self._make_entity()
        await entity.async_set_clean()
        entity.coordinator.client.set_clean.assert_called_once_with(True)
