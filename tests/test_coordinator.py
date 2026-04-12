"""Tests for the Ooler coordinator."""

from __future__ import annotations

import asyncio
from datetime import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util.unit_system import METRIC_SYSTEM
from ooler_ble_client import OolerSleepSchedule, SleepScheduleNight

from custom_components.ooler.coordinator import (
    CLOCK_SYNC_INTERVAL,
    OolerCoordinator,
    _deserialize_schedule,
    _serialize_schedule,
)

from .conftest import (
    OOLER_ADDRESS,
    OOLER_NAME,
    make_empty_schedule,
    make_mock_client,
    make_mock_schedule,
)


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
    hass.config.time_zone = "UTC"
    hass.async_create_task = MagicMock(side_effect=lambda coro, **_kw: coro.close())
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
    coordinator, _client = make_coordinator(connected=False)
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
    """Test coordinator stop disables reconnect and disconnects the client."""
    coordinator, client = make_coordinator()

    await coordinator.async_stop()
    assert coordinator.connection_enabled is False
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

    # BLE callback, state callback, reconnect timer, poll timer, clock sync timer, HA stop
    assert len(cleanups) == 6


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
    assert len(cleanups) == 6


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
    coordinator.hass.async_create_task.side_effect = lambda coro, **_kw: (
        coro.close(),
        running_task,
    )[1]

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
    coordinator, _client = make_coordinator()

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


async def test_coordinator_post_connect_reads_schedule() -> None:
    """Test post-connect reads sleep schedule and caches it."""
    coordinator, client = make_coordinator(connected=False)
    schedule = make_mock_schedule()
    client.read_sleep_schedule = AsyncMock(return_value=schedule)

    await coordinator._async_post_connect()

    client.read_sleep_schedule.assert_called_once()
    assert coordinator._cached_sleep_schedule is schedule
    client.sync_clock.assert_called_once()


async def test_coordinator_post_connect_empty_schedule_not_cached() -> None:
    """Test post-connect does not cache an empty schedule."""
    coordinator, client = make_coordinator()
    client.read_sleep_schedule = AsyncMock(return_value=make_empty_schedule())

    await coordinator._async_post_connect()

    assert coordinator._cached_sleep_schedule is None


async def test_coordinator_post_connect_clears_stale_saved_name() -> None:
    """Test post-connect clears active_saved_name when device schedule changed."""
    coordinator, client = make_coordinator()
    saved_schedule = make_mock_schedule()
    coordinator._saved_schedules = {"weekday": saved_schedule}
    coordinator._active_saved_name = "weekday"

    # Device now has a different schedule (different night)
    different_schedule = OolerSleepSchedule(
        nights=[
            SleepScheduleNight(
                day=5,
                temps=[(time(23, 0), 70)],
                off_time=time(8, 0),
                warm_wake=None,
            )
        ],
        seq=10,
    )
    client.read_sleep_schedule = AsyncMock(return_value=different_schedule)

    await coordinator._async_post_connect()

    assert coordinator._active_saved_name is None


async def test_coordinator_post_connect_keeps_matching_saved_name() -> None:
    """Test post-connect keeps active_saved_name when device schedule matches."""
    coordinator, client = make_coordinator()
    saved_schedule = make_mock_schedule()
    coordinator._saved_schedules = {"weekday": saved_schedule}
    coordinator._active_saved_name = "weekday"

    # Device has same nights but different seq (seq changes on each write)
    matching_schedule = OolerSleepSchedule(
        nights=saved_schedule.nights,
        seq=99,
    )
    client.read_sleep_schedule = AsyncMock(return_value=matching_schedule)

    await coordinator._async_post_connect()

    assert coordinator._active_saved_name == "weekday"


async def test_coordinator_post_connect_clears_deleted_saved_name() -> None:
    """Test post-connect clears active_saved_name if the saved schedule was deleted."""
    coordinator, client = make_coordinator()
    coordinator._saved_schedules = {}  # schedule was deleted
    coordinator._active_saved_name = "weekday"

    client.read_sleep_schedule = AsyncMock(return_value=make_mock_schedule())

    await coordinator._async_post_connect()

    assert coordinator._active_saved_name is None


async def test_coordinator_post_connect_schedule_read_failure() -> None:
    """Test post-connect handles schedule read failure gracefully."""
    coordinator, client = make_coordinator()
    client.read_sleep_schedule = AsyncMock(side_effect=BleakError("read failed"))

    await coordinator._async_post_connect()

    assert coordinator._cached_sleep_schedule is None
    # Clock sync still attempted after schedule read failure
    client.sync_clock.assert_called_once()


async def test_coordinator_sync_clock() -> None:
    """Test clock sync sends HA timezone to device."""
    coordinator, client = make_coordinator()
    coordinator.hass.config.time_zone = "America/New_York"

    await coordinator._async_sync_clock()

    client.sync_clock.assert_called_once()
    call_arg = client.sync_clock.call_args[0][0]
    assert call_arg.tzinfo is not None


async def test_coordinator_sync_clock_failure() -> None:
    """Test clock sync handles failure gracefully."""
    coordinator, client = make_coordinator()
    coordinator.hass.config.time_zone = "America/New_York"
    client.sync_clock = AsyncMock(side_effect=TimeoutError)

    await coordinator._async_sync_clock()  # should not raise


async def test_coordinator_clock_sync_check_connected() -> None:
    """Test clock sync check creates task when connected."""
    coordinator, _ = make_coordinator(connected=True)

    coordinator._async_clock_sync_check()
    coordinator.hass.async_create_task.assert_called_once()


async def test_coordinator_clock_sync_check_disconnected() -> None:
    """Test clock sync check is no-op when disconnected."""
    coordinator, _ = make_coordinator(connected=False)

    coordinator._async_clock_sync_check()
    coordinator.hass.async_create_task.assert_not_called()


async def test_coordinator_clock_sync_check_disabled() -> None:
    """Test clock sync check is no-op when connection disabled."""
    coordinator, _ = make_coordinator(connected=True)
    coordinator.connection_enabled = False

    coordinator._async_clock_sync_check()
    coordinator.hass.async_create_task.assert_not_called()


async def test_coordinator_cached_sleep_schedule_property() -> None:
    """Test cached_sleep_schedule property returns cached value."""
    coordinator, _ = make_coordinator()
    assert coordinator.cached_sleep_schedule is None

    schedule = make_mock_schedule()
    coordinator._cached_sleep_schedule = schedule
    assert coordinator.cached_sleep_schedule is schedule


async def test_coordinator_sleep_schedule_active() -> None:
    """Test sleep_schedule_active property."""
    coordinator, client = make_coordinator()
    schedule = make_mock_schedule()
    client.sleep_schedule = schedule

    assert coordinator.sleep_schedule_active is True


async def test_coordinator_sleep_schedule_not_active() -> None:
    """Test sleep_schedule_active is False when no schedule."""
    coordinator, client = make_coordinator()
    client.sleep_schedule = None

    assert coordinator.sleep_schedule_active is False


async def test_coordinator_sleep_schedule_empty_not_active() -> None:
    """Test sleep_schedule_active is False with empty nights."""
    coordinator, client = make_coordinator()
    client.sleep_schedule = make_empty_schedule()

    assert coordinator.sleep_schedule_active is False


async def test_coordinator_enable_sleep_schedule() -> None:
    """Test enabling the cached sleep schedule."""
    coordinator, client = make_coordinator()
    schedule = make_mock_schedule()
    coordinator._cached_sleep_schedule = schedule

    listener_called = False

    def listener() -> None:
        nonlocal listener_called
        listener_called = True

    coordinator.async_add_listener(listener)
    await coordinator.async_enable_sleep_schedule()

    client.set_sleep_schedule.assert_called_once_with(schedule.nights)
    assert listener_called


async def test_coordinator_enable_sleep_schedule_no_cache() -> None:
    """Test enabling sleep schedule raises when no cache."""
    coordinator, _ = make_coordinator()
    coordinator._cached_sleep_schedule = None

    with pytest.raises(HomeAssistantError, match="No cached sleep schedule"):
        await coordinator.async_enable_sleep_schedule()


async def test_coordinator_disable_sleep_schedule() -> None:
    """Test disabling the sleep schedule caches and clears."""
    coordinator, client = make_coordinator()
    schedule = make_mock_schedule()
    client.sleep_schedule = schedule

    listener_called = False

    def listener() -> None:
        nonlocal listener_called
        listener_called = True

    coordinator.async_add_listener(listener)
    await coordinator.async_disable_sleep_schedule()

    assert coordinator._cached_sleep_schedule is schedule
    client.clear_sleep_schedule.assert_called_once()
    assert listener_called


async def test_coordinator_disable_sleep_schedule_already_empty() -> None:
    """Test disabling when no active schedule still clears device."""
    coordinator, client = make_coordinator()
    client.sleep_schedule = None

    await coordinator.async_disable_sleep_schedule()

    client.clear_sleep_schedule.assert_called_once()
    assert coordinator._cached_sleep_schedule is None


async def test_coordinator_async_start_has_clock_sync_timer(
    hass: HomeAssistant,
) -> None:
    """Test async_start registers clock sync timer."""
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
        ) as mock_track,
    ):
        cleanups = await coordinator.async_start()

    # BLE callback, state callback, reconnect timer, poll timer, clock sync timer, HA stop
    assert len(cleanups) == 6
    # Verify clock sync timer was registered with correct interval
    intervals = [call.args[2] for call in mock_track.call_args_list]
    assert CLOCK_SYNC_INTERVAL in intervals


async def test_coordinator_connect_calls_post_connect() -> None:
    """Test _async_connect calls _async_post_connect after unit sync."""
    coordinator, client = make_coordinator(connected=False)
    client.state.temperature_unit = "F"
    coordinator._ha_unit = "F"
    schedule = make_mock_schedule()
    client.read_sleep_schedule = AsyncMock(return_value=schedule)
    coordinator.hass.config.time_zone = "UTC"

    await coordinator._async_connect()

    client.read_sleep_schedule.assert_called_once()
    client.sync_clock.assert_called_once()
    assert coordinator._cached_sleep_schedule is schedule


# --- Serialization tests ---


class TestScheduleSerialization:
    """Tests for schedule serialization and deserialization."""

    def test_round_trip(self) -> None:
        """Test serialize -> deserialize produces equivalent schedule."""
        original = make_mock_schedule()
        data = _serialize_schedule(original)
        restored = _deserialize_schedule(data)

        assert len(restored.nights) == len(original.nights)
        for orig_night, rest_night in zip(
            original.nights, restored.nights, strict=True
        ):
            assert orig_night.day == rest_night.day
            assert orig_night.off_time == rest_night.off_time
            assert orig_night.temps == rest_night.temps
            if orig_night.warm_wake is not None:
                assert rest_night.warm_wake is not None
                assert (
                    orig_night.warm_wake.target_temp_f
                    == rest_night.warm_wake.target_temp_f
                )
                assert (
                    orig_night.warm_wake.duration_min
                    == rest_night.warm_wake.duration_min
                )
            else:
                assert rest_night.warm_wake is None
        assert restored.seq == original.seq

    def test_serialize_no_warm_wake(self) -> None:
        """Test serialization with no warm wake."""
        schedule = OolerSleepSchedule(
            nights=[
                SleepScheduleNight(
                    day=0,
                    temps=[(time(22, 0), 68)],
                    off_time=time(6, 0),
                    warm_wake=None,
                )
            ],
            seq=1,
        )
        data = _serialize_schedule(schedule)
        assert data["nights"][0]["warm_wake"] is None

        restored = _deserialize_schedule(data)
        assert restored.nights[0].warm_wake is None

    def test_serialize_multiple_temps(self) -> None:
        """Test serialization preserves multiple temp zones."""
        schedule = OolerSleepSchedule(
            nights=[
                SleepScheduleNight(
                    day=0,
                    temps=[
                        (time(22, 0), 68),
                        (time(2, 0), 62),
                        (time(4, 0), 70),
                    ],
                    off_time=time(6, 0),
                    warm_wake=None,
                )
            ],
            seq=1,
        )
        data = _serialize_schedule(schedule)
        restored = _deserialize_schedule(data)

        assert len(restored.nights[0].temps) == 3
        assert restored.nights[0].temps[1] == (time(2, 0), 62)

    def test_deserialize_missing_seq(self) -> None:
        """Test deserialization defaults seq to 0."""
        data = {
            "nights": [
                {
                    "day": 0,
                    "temps": [["22:00", 68]],
                    "off_time": "06:00",
                    "warm_wake": None,
                }
            ]
        }
        schedule = _deserialize_schedule(data)
        assert schedule.seq == 0


# --- Tonight schedule tests ---


async def test_coordinator_tonight_schedule_with_match() -> None:
    """Test tonight_schedule returns matching night."""
    coordinator, client = make_coordinator()
    schedule = make_mock_schedule()
    client.sleep_schedule = schedule
    coordinator.hass.config.time_zone = "UTC"

    with patch(
        "custom_components.ooler.coordinator.datetime"
    ) as mock_dt:
        mock_now = MagicMock()
        mock_now.weekday.return_value = 0  # Monday
        mock_dt.now.return_value = mock_now
        result = coordinator.tonight_schedule

    assert result is not None
    assert result.day == 0


async def test_coordinator_tonight_schedule_no_match() -> None:
    """Test tonight_schedule returns None when day not in schedule."""
    coordinator, client = make_coordinator()
    schedule = make_mock_schedule()  # Has day 0 and day 1
    client.sleep_schedule = schedule
    coordinator.hass.config.time_zone = "UTC"

    with patch(
        "custom_components.ooler.coordinator.datetime"
    ) as mock_dt:
        mock_now = MagicMock()
        mock_now.weekday.return_value = 5  # Saturday
        mock_dt.now.return_value = mock_now
        result = coordinator.tonight_schedule

    assert result is None


async def test_coordinator_tonight_schedule_no_schedule() -> None:
    """Test tonight_schedule returns None when no schedule."""
    coordinator, client = make_coordinator()
    client.sleep_schedule = None

    assert coordinator.tonight_schedule is None


async def test_coordinator_tonight_schedule_empty() -> None:
    """Test tonight_schedule returns None with empty schedule."""
    coordinator, client = make_coordinator()
    client.sleep_schedule = make_empty_schedule()

    assert coordinator.tonight_schedule is None


# --- Storage tests ---


async def test_coordinator_load_store_empty() -> None:
    """Test loading store when no data exists."""
    coordinator, _ = make_coordinator()
    coordinator._store = MagicMock()
    coordinator._store.async_load = AsyncMock(return_value=None)

    await coordinator.async_load_store()

    assert coordinator._saved_schedules == {}


async def test_coordinator_load_store_with_data() -> None:
    """Test loading store restores saved schedules."""
    coordinator, _ = make_coordinator()
    schedule = make_mock_schedule()
    serialized = _serialize_schedule(schedule)

    coordinator._store = MagicMock()
    coordinator._store.async_load = AsyncMock(
        return_value={"schedules": {"weekday": serialized}}
    )

    await coordinator.async_load_store()

    assert "weekday" in coordinator._saved_schedules
    assert len(coordinator._saved_schedules["weekday"].nights) == 2


async def test_coordinator_save_schedule() -> None:
    """Test saving the current device schedule."""
    coordinator, client = make_coordinator()
    schedule = make_mock_schedule()
    client.sleep_schedule = schedule
    coordinator._store = MagicMock()
    coordinator._store.async_save = AsyncMock()

    listener_called = False

    def listener() -> None:
        nonlocal listener_called
        listener_called = True

    coordinator.async_add_listener(listener)
    await coordinator.async_save_schedule("weekday")

    assert "weekday" in coordinator._saved_schedules
    assert coordinator._active_saved_name == "weekday"
    coordinator._store.async_save.assert_called_once()
    assert listener_called


async def test_coordinator_save_schedule_no_active() -> None:
    """Test saving raises when no active schedule."""
    coordinator, client = make_coordinator()
    client.sleep_schedule = None

    with pytest.raises(HomeAssistantError, match="No active schedule"):
        await coordinator.async_save_schedule("test")


async def test_coordinator_save_schedule_empty_active() -> None:
    """Test saving raises when schedule has no nights."""
    coordinator, client = make_coordinator()
    client.sleep_schedule = make_empty_schedule()

    with pytest.raises(HomeAssistantError, match="No active schedule"):
        await coordinator.async_save_schedule("test")


async def test_coordinator_delete_saved_schedule() -> None:
    """Test deleting a saved schedule."""
    coordinator, _ = make_coordinator()
    coordinator._saved_schedules = {"weekday": make_mock_schedule()}
    coordinator._active_saved_name = "weekday"
    coordinator._store = MagicMock()
    coordinator._store.async_save = AsyncMock()

    listener_called = False

    def listener() -> None:
        nonlocal listener_called
        listener_called = True

    coordinator.async_add_listener(listener)
    await coordinator.async_delete_saved_schedule("weekday")

    assert "weekday" not in coordinator._saved_schedules
    assert coordinator._active_saved_name is None
    coordinator._store.async_save.assert_called_once()
    assert listener_called


async def test_coordinator_delete_saved_schedule_not_active() -> None:
    """Test deleting a schedule that isn't the active one."""
    coordinator, _ = make_coordinator()
    coordinator._saved_schedules = {
        "weekday": make_mock_schedule(),
        "weekend": make_mock_schedule(),
    }
    coordinator._active_saved_name = "weekday"
    coordinator._store = MagicMock()
    coordinator._store.async_save = AsyncMock()

    await coordinator.async_delete_saved_schedule("weekend")

    assert coordinator._active_saved_name == "weekday"  # unchanged


async def test_coordinator_delete_saved_schedule_not_found() -> None:
    """Test deleting a nonexistent schedule raises."""
    coordinator, _ = make_coordinator()

    with pytest.raises(HomeAssistantError, match="No saved schedule named"):
        await coordinator.async_delete_saved_schedule("nonexistent")


async def test_coordinator_load_saved_schedule() -> None:
    """Test loading a saved schedule writes to device."""
    coordinator, client = make_coordinator()
    schedule = make_mock_schedule()
    coordinator._saved_schedules = {"weekday": schedule}
    coordinator._store = MagicMock()

    listener_called = False

    def listener() -> None:
        nonlocal listener_called
        listener_called = True

    coordinator.async_add_listener(listener)
    await coordinator.async_load_saved_schedule("weekday")

    client.set_sleep_schedule.assert_called_once_with(schedule.nights)
    assert coordinator._active_saved_name == "weekday"
    assert listener_called


async def test_coordinator_load_saved_schedule_not_found() -> None:
    """Test loading a nonexistent schedule raises."""
    coordinator, _ = make_coordinator()

    with pytest.raises(HomeAssistantError, match="No saved schedule named"):
        await coordinator.async_load_saved_schedule("nonexistent")


async def test_coordinator_write_sleep_schedule() -> None:
    """Test writing a schedule directly to device."""
    coordinator, client = make_coordinator()
    nights = make_mock_schedule().nights

    listener_called = False

    def listener() -> None:
        nonlocal listener_called
        listener_called = True

    coordinator.async_add_listener(listener)
    await coordinator.async_write_sleep_schedule(nights)

    client.set_sleep_schedule.assert_called_once_with(nights)
    assert coordinator._active_saved_name is None
    assert listener_called


async def test_coordinator_disable_clears_active_name() -> None:
    """Test disabling schedule clears the active saved name."""
    coordinator, client = make_coordinator()
    schedule = make_mock_schedule()
    client.sleep_schedule = schedule
    coordinator._active_saved_name = "weekday"

    await coordinator.async_disable_sleep_schedule()

    assert coordinator._active_saved_name is None


async def test_coordinator_saved_schedules_property() -> None:
    """Test saved_schedules property returns the dict."""
    coordinator, _ = make_coordinator()
    schedule = make_mock_schedule()
    coordinator._saved_schedules = {"test": schedule}

    assert coordinator.saved_schedules == {"test": schedule}


async def test_coordinator_active_saved_name_property() -> None:
    """Test active_saved_name property."""
    coordinator, _ = make_coordinator()
    assert coordinator.active_saved_name is None

    coordinator._active_saved_name = "test"
    assert coordinator.active_saved_name == "test"


async def test_coordinator_async_start_loads_store(
    hass: HomeAssistant,
) -> None:
    """Test async_start loads the schedule store."""
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
        patch.object(
            coordinator, "async_load_store", new_callable=AsyncMock
        ) as mock_load,
    ):
        await coordinator.async_start()

    mock_load.assert_called_once()
