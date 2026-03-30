"""Tests for the Ooler coordinator."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util.unit_system import METRIC_SYSTEM

from custom_components.ooler.coordinator import OolerCoordinator

from .conftest import OOLER_ADDRESS, OOLER_NAME, make_mock_client


def make_mock_entry() -> MagicMock:
    """Create a minimal mock config entry for coordinator."""
    entry = MagicMock()
    entry.unique_id = OOLER_ADDRESS
    entry.data = {"model": OOLER_NAME}
    return entry


def make_mock_hass() -> MagicMock:
    """Create a mock HomeAssistant for coordinator tests."""
    hass = MagicMock()
    hass.config = MagicMock()
    hass.config.units = METRIC_SYSTEM
    hass.async_create_task = MagicMock(side_effect=lambda coro, **kw: coro.close())
    hass.bus = MagicMock()
    return hass


def make_coordinator(
    *, connected: bool = True, hass: MagicMock | None = None
) -> tuple[OolerCoordinator, MagicMock]:
    """Create a coordinator with a mocked client."""
    if hass is None:
        hass = make_mock_hass()
    client = make_mock_client(connected=connected)
    entry = make_mock_entry()
    with patch(
        "custom_components.ooler.coordinator.OolerBLEDevice",
        return_value=client,
    ):
        coordinator = OolerCoordinator(hass, entry)
    return coordinator, client


async def test_coordinator_init() -> None:
    """Test coordinator initializes with correct state."""
    coordinator, _ = make_coordinator()
    assert coordinator.address == OOLER_ADDRESS
    assert coordinator.model == OOLER_NAME
    assert coordinator.connection_enabled is True
    assert coordinator._unit_synced is False


async def test_coordinator_connect() -> None:
    """Test coordinator connects and syncs temperature unit."""
    coordinator, client = make_coordinator(connected=False)
    client.state.temperature_unit = "F"
    coordinator._ha_unit = "C"

    await coordinator._async_connect()

    client.connect.assert_called_once()
    client.set_temperature_unit.assert_called_once_with("C")
    assert coordinator._unit_synced is True


async def test_coordinator_connect_unit_already_synced() -> None:
    """Test coordinator skips unit sync when already matching."""
    coordinator, client = make_coordinator()
    client.state.temperature_unit = "C"
    coordinator._ha_unit = "C"

    await coordinator._async_connect()

    client.connect.assert_called_once()
    client.set_temperature_unit.assert_not_called()
    assert coordinator._unit_synced is True


async def test_coordinator_connect_failure() -> None:
    """Test coordinator handles connection failure gracefully."""
    coordinator, client = make_coordinator(connected=False)
    client.connect = AsyncMock(side_effect=TimeoutError)

    await coordinator._async_connect()

    assert coordinator._unit_synced is False


async def test_coordinator_ensure_connected_raises() -> None:
    """Test async_ensure_connected raises HomeAssistantError on failure."""
    from homeassistant.exceptions import HomeAssistantError

    coordinator, client = make_coordinator(connected=False)
    client.connect = AsyncMock(side_effect=TimeoutError)

    with pytest.raises(HomeAssistantError):
        await coordinator.async_ensure_connected()


async def test_coordinator_ensure_connected_already_connected() -> None:
    """Test async_ensure_connected is a no-op when already connected."""
    coordinator, client = make_coordinator(connected=True)

    await coordinator.async_ensure_connected()
    client.connect.assert_not_called()


async def test_coordinator_ensure_connected_awaits_inflight_task() -> None:
    """Test async_ensure_connected awaits in-flight connect task."""
    coordinator, client = make_coordinator(connected=False)

    # Simulate an in-flight connect task that will succeed
    async def fake_connect() -> None:
        client.is_connected = True

    task = asyncio.ensure_future(fake_connect())
    coordinator._connect_task = task

    await coordinator.async_ensure_connected()

    # Should not have called connect() directly — the in-flight task handled it
    client.connect.assert_not_called()


async def test_coordinator_ensure_connected_inflight_task_fails() -> None:
    """Test async_ensure_connected retries if in-flight task didn't connect."""
    coordinator, client = make_coordinator(connected=False)

    # Simulate an in-flight connect task that completes but doesn't connect
    async def fake_connect_fail() -> None:
        pass  # doesn't set is_connected

    task = asyncio.ensure_future(fake_connect_fail())
    coordinator._connect_task = task

    await coordinator.async_ensure_connected()

    # Should have called connect() since in-flight task didn't connect
    client.connect.assert_called_once()


async def test_coordinator_connection_disabled_skips_reconnect() -> None:
    """Test reconnect is suppressed when connection_enabled is False."""
    coordinator, client = make_coordinator(connected=False)
    coordinator.connection_enabled = False

    coordinator._async_reconnect_check()

    coordinator.hass.async_create_task.assert_not_called()


async def test_coordinator_poll() -> None:
    """Test periodic polling calls async_poll."""
    coordinator, client = make_coordinator(connected=True)

    await coordinator._async_poll()
    client.async_poll.assert_called_once()


async def test_coordinator_poll_failure() -> None:
    """Test poll failure is handled gracefully."""
    coordinator, client = make_coordinator(connected=True)
    client.async_poll = AsyncMock(side_effect=TimeoutError)

    await coordinator._async_poll()


async def test_coordinator_listeners() -> None:
    """Test listener registration and notification."""
    coordinator, _ = make_coordinator()

    callback_called = False

    def listener() -> None:
        nonlocal callback_called
        callback_called = True

    remove = coordinator.async_add_listener(listener)
    coordinator._async_notify_listeners()
    assert callback_called

    callback_called = False
    remove()
    coordinator._async_notify_listeners()
    assert not callback_called


async def test_coordinator_stop() -> None:
    """Test coordinator stop disconnects the client."""
    coordinator, client = make_coordinator()

    await coordinator.async_stop()
    client.stop.assert_called_once()


async def test_coordinator_async_start(hass: HomeAssistant) -> None:
    """Test async_start registers callbacks and returns cleanup list."""
    entry = make_mock_entry()

    with patch(
        "custom_components.ooler.coordinator.OolerBLEDevice",
        return_value=make_mock_client(),
    ):
        coordinator = OolerCoordinator(hass, entry)

    with (
        patch(
            "custom_components.ooler.coordinator.async_ble_device_from_address",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.ooler.coordinator.async_register_callback",
            return_value=lambda: None,
        ),
        patch(
            "custom_components.ooler.coordinator.async_track_time_interval",
            return_value=lambda: None,
        ),
    ):
        cleanups = await coordinator.async_start()

    # BLE callback, state callback, reconnect timer, poll timer, HA stop
    assert len(cleanups) == 5


async def test_coordinator_async_start_no_ble_device(
    hass: HomeAssistant,
) -> None:
    """Test async_start handles missing BLEDevice gracefully."""
    client = make_mock_client()
    entry = make_mock_entry()

    with patch(
        "custom_components.ooler.coordinator.OolerBLEDevice",
        return_value=client,
    ):
        coordinator = OolerCoordinator(hass, entry)

    with (
        patch(
            "custom_components.ooler.coordinator.async_ble_device_from_address",
            return_value=None,
        ),
        patch(
            "custom_components.ooler.coordinator.async_register_callback",
            return_value=lambda: None,
        ),
        patch(
            "custom_components.ooler.coordinator.async_track_time_interval",
            return_value=lambda: None,
        ),
    ):
        cleanups = await coordinator.async_start()

    client.set_ble_device.assert_not_called()
    assert len(cleanups) == 5


async def test_coordinator_update_ble_connected() -> None:
    """Test BLE callback updates device but doesn't reconnect when connected."""
    coordinator, client = make_coordinator(connected=True)

    service_info = MagicMock()
    service_info.device = MagicMock()

    coordinator._async_update_ble(service_info, MagicMock())

    client.set_ble_device.assert_called_once_with(service_info.device)
    coordinator.hass.async_create_task.assert_not_called()


async def test_coordinator_update_ble_disconnected() -> None:
    """Test BLE callback triggers reconnect when disconnected."""
    coordinator, client = make_coordinator(connected=False)

    service_info = MagicMock()
    service_info.device = MagicMock()

    coordinator._async_update_ble(service_info, MagicMock())

    client.set_ble_device.assert_called_once()
    coordinator.hass.async_create_task.assert_called_once()


async def test_coordinator_state_change_reconnect() -> None:
    """Test state change triggers reconnect when disconnected."""
    coordinator, _ = make_coordinator(connected=False)

    listener_called = False

    def listener() -> None:
        nonlocal listener_called
        listener_called = True

    coordinator.async_add_listener(listener)
    coordinator._async_on_state_change()

    assert listener_called
    coordinator.hass.async_create_task.assert_called_once()


async def test_coordinator_state_change_connected() -> None:
    """Test state change notifies listeners without reconnect when connected."""
    coordinator, _ = make_coordinator(connected=True)

    listener_called = False

    def listener() -> None:
        nonlocal listener_called
        listener_called = True

    coordinator.async_add_listener(listener)
    coordinator._async_on_state_change()

    assert listener_called
    coordinator.hass.async_create_task.assert_not_called()


async def test_coordinator_schedule_connect_dedup() -> None:
    """Test _schedule_connect deduplicates concurrent attempts."""
    coordinator, _ = make_coordinator()

    running_task = MagicMock()
    running_task.done.return_value = False
    coordinator.hass.async_create_task.side_effect = (
        lambda coro, **kw: (coro.close(), running_task)[1]
    )

    coordinator._schedule_connect()
    assert coordinator.hass.async_create_task.call_count == 1

    coordinator._schedule_connect()
    assert coordinator.hass.async_create_task.call_count == 1


async def test_coordinator_reconnect_check_connected() -> None:
    """Test reconnect check is no-op when connected."""
    coordinator, _ = make_coordinator(connected=True)

    coordinator._async_reconnect_check()
    coordinator.hass.async_create_task.assert_not_called()


async def test_coordinator_reconnect_check_with_fresh_device() -> None:
    """Test reconnect check refreshes BLEDevice before reconnecting."""
    coordinator, client = make_coordinator(connected=False)

    fresh_device = MagicMock()
    with patch(
        "custom_components.ooler.coordinator.async_ble_device_from_address",
        return_value=fresh_device,
    ):
        coordinator._async_reconnect_check()

    client.set_ble_device.assert_called_with(fresh_device)
    coordinator.hass.async_create_task.assert_called_once()


async def test_coordinator_reconnect_check_no_fresh_device() -> None:
    """Test reconnect check proceeds without fresh device."""
    coordinator, _ = make_coordinator(connected=False)

    with patch(
        "custom_components.ooler.coordinator.async_ble_device_from_address",
        return_value=None,
    ):
        coordinator._async_reconnect_check()

    coordinator.hass.async_create_task.assert_called_once()


async def test_coordinator_poll_check_connected() -> None:
    """Test poll check creates task when connected."""
    coordinator, _ = make_coordinator(connected=True)

    coordinator._async_poll_check()
    coordinator.hass.async_create_task.assert_called_once()


async def test_coordinator_poll_check_disconnected() -> None:
    """Test poll check is no-op when disconnected."""
    coordinator, _ = make_coordinator(connected=False)

    coordinator._async_poll_check()
    coordinator.hass.async_create_task.assert_not_called()


async def test_coordinator_poll_check_disabled() -> None:
    """Test poll check is no-op when connection disabled."""
    coordinator, _ = make_coordinator(connected=True)
    coordinator.connection_enabled = False

    coordinator._async_poll_check()
    coordinator.hass.async_create_task.assert_not_called()


async def test_coordinator_async_stop_event() -> None:
    """Test _async_stop event handler disconnects."""
    coordinator, client = make_coordinator()

    await coordinator._async_stop(MagicMock())
    client.stop.assert_called_once()


async def test_coordinator_stagger_connect() -> None:
    """Test staggered connect applies delay."""
    coordinator, client = make_coordinator()

    with patch("custom_components.ooler.coordinator.asyncio.sleep") as mock_sleep:
        await coordinator._async_connect(stagger=True)
        mock_sleep.assert_called_once_with(coordinator._reconnect_delay)


async def test_coordinator_is_connected() -> None:
    """Test is_connected property delegates to client."""
    coordinator, _ = make_coordinator(connected=True)
    assert coordinator.is_connected is True

    coordinator, _ = make_coordinator(connected=False)
    assert coordinator.is_connected is False


async def test_coordinator_state_change_disabled() -> None:
    """Test state change does not reconnect when connection_enabled is False."""
    coordinator, _ = make_coordinator(connected=False)
    coordinator.connection_enabled = False

    listener_called = False

    def listener() -> None:
        nonlocal listener_called
        listener_called = True

    coordinator.async_add_listener(listener)
    coordinator._async_on_state_change()

    assert listener_called  # listeners still notified
    coordinator.hass.async_create_task.assert_not_called()  # no reconnect


async def test_coordinator_update_ble_disconnected_disabled() -> None:
    """Test BLE callback does not reconnect when connection_enabled is False."""
    coordinator, client = make_coordinator(connected=False)
    coordinator.connection_enabled = False

    service_info = MagicMock()
    service_info.device = MagicMock()

    coordinator._async_update_ble(service_info, MagicMock())

    client.set_ble_device.assert_called_once()  # device still updated
    coordinator.hass.async_create_task.assert_not_called()  # no reconnect
