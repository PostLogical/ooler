"""Tests for the Ooler diagnostics platform."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.ooler.coordinator import OolerCoordinator
from custom_components.ooler.diagnostics import async_get_config_entry_diagnostics

from .conftest import (
    OOLER_ADDRESS,
    OOLER_NAME,
    make_mock_client,
    make_mock_schedule,
)


async def test_diagnostics(hass) -> None:
    """Test diagnostics returns expected data structure."""
    client = make_mock_client()
    coordinator = MagicMock(spec=OolerCoordinator)
    coordinator.client = client
    coordinator.connection_enabled = True
    coordinator.last_notification_stall = None
    coordinator.forced_reconnect_counts = {}

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
    assert result["sleep_schedule"]["active"] is False
    assert result["connection_events"]["last_notification_stall"] is None
    assert result["connection_events"]["forced_reconnect_counts"] == {}


async def test_diagnostics_with_schedule(hass) -> None:
    """Test diagnostics includes sleep schedule data when active."""
    client = make_mock_client()
    client.sleep_schedule = make_mock_schedule()
    coordinator = MagicMock(spec=OolerCoordinator)
    coordinator.client = client
    coordinator.connection_enabled = True
    coordinator.last_notification_stall = None
    coordinator.forced_reconnect_counts = {}

    entry = MagicMock()
    entry.unique_id = OOLER_ADDRESS
    entry.data = {"model": OOLER_NAME}
    entry.runtime_data = coordinator

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["sleep_schedule"]["active"] is True
    assert result["sleep_schedule"]["seq"] == 5
    assert result["sleep_schedule"]["night_count"] == 2
    assert result["sleep_schedule"]["days"] == [0, 1]


async def test_diagnostics_with_connection_events(hass) -> None:
    """Test diagnostics includes connection event data when present."""
    client = make_mock_client()
    coordinator = MagicMock(spec=OolerCoordinator)
    coordinator.client = client
    coordinator.connection_enabled = True
    coordinator.last_notification_stall = {
        "timestamp": "2026-04-12T03:15:00",
        "stall_duration_seconds": 920.5,
    }
    coordinator.forced_reconnect_counts = {"notify_stall": 2, "poll_failure": 1}

    entry = MagicMock()
    entry.unique_id = OOLER_ADDRESS
    entry.data = {"model": OOLER_NAME}
    entry.runtime_data = coordinator

    result = await async_get_config_entry_diagnostics(hass, entry)

    stall = result["connection_events"]["last_notification_stall"]
    assert stall["stall_duration_seconds"] == 920.5
    assert stall["timestamp"] == "2026-04-12T03:15:00"
    assert result["connection_events"]["forced_reconnect_counts"] == {
        "notify_stall": 2,
        "poll_failure": 1,
    }
