"""Tests for the Ooler diagnostics platform."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.ooler.coordinator import OolerCoordinator
from custom_components.ooler.diagnostics import async_get_config_entry_diagnostics

from .conftest import OOLER_ADDRESS, OOLER_NAME, make_mock_client


async def test_diagnostics(hass) -> None:
    """Test diagnostics returns expected data structure."""
    client = make_mock_client()
    coordinator = MagicMock(spec=OolerCoordinator)
    coordinator.client = client
    coordinator.connection_enabled = True

    entry = MagicMock()
    entry.unique_id = OOLER_ADDRESS
    entry.data = {"model": OOLER_NAME}
    entry.runtime_data = coordinator

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["config_entry"]["unique_id"] == OOLER_ADDRESS
    assert result["connection"]["is_connected"] is True
    assert result["connection"]["connection_enabled"] is True
    assert result["device_state"]["power"] is True
    assert result["device_state"]["mode"] == "Regular"
    assert result["device_state"]["set_temperature"] == 72
    assert result["device_state"]["actual_temperature"] == 74
    assert result["device_state"]["temperature_unit"] == "F"
    assert result["device_state"]["water_level"] == 80
    assert result["device_state"]["clean"] is False
