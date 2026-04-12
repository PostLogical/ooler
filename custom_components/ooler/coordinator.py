"""Coordinator for the Ooler Sleep System integration."""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from bleak.exc import BleakError
from homeassistant.components.bluetooth import (
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
    async_register_callback,
)
from homeassistant.components.bluetooth.match import ADDRESS
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util.unit_system import METRIC_SYSTEM
from ooler_ble_client import (
    OolerBLEDevice,
    OolerSleepSchedule,
    SleepScheduleNight,
    TemperatureUnit,
    WarmWake,
)

from .const import _LOGGER, CONF_MODEL, DOMAIN

if TYPE_CHECKING:
    from collections.abc import Callable

RECONNECT_INTERVAL = timedelta(seconds=60)
POLL_INTERVAL = timedelta(minutes=5)
CLOCK_SYNC_INTERVAL = timedelta(hours=4)

STORAGE_VERSION = 1


def _serialize_schedule(schedule: OolerSleepSchedule) -> dict[str, Any]:
    """Serialize an OolerSleepSchedule to a JSON-compatible dict."""
    nights = []
    for night in schedule.nights:
        night_dict: dict[str, Any] = {
            "day": night.day,
            "temps": [[t.strftime("%H:%M"), temp] for t, temp in night.temps],
            "off_time": night.off_time.strftime("%H:%M"),
        }
        if night.warm_wake is not None:
            night_dict["warm_wake"] = {
                "target_temp_f": night.warm_wake.target_temp_f,
                "duration_min": night.warm_wake.duration_min,
            }
        else:
            night_dict["warm_wake"] = None
        nights.append(night_dict)
    return {"nights": nights, "seq": schedule.seq}


def _deserialize_schedule(data: dict[str, Any]) -> OolerSleepSchedule:
    """Deserialize a JSON dict back to an OolerSleepSchedule."""
    nights = []
    for night_data in data["nights"]:
        warm_wake = None
        if night_data.get("warm_wake") is not None:
            ww = night_data["warm_wake"]
            warm_wake = WarmWake(
                target_temp_f=ww["target_temp_f"],
                duration_min=ww["duration_min"],
            )
        temps = []
        for time_str, temp_f in night_data["temps"]:
            h, m = time_str.split(":")
            temps.append((time(int(h), int(m)), temp_f))
        nights.append(
            SleepScheduleNight(
                day=night_data["day"],
                temps=temps,
                off_time=time(*map(int, night_data["off_time"].split(":"))),
                warm_wake=warm_wake,
            )
        )
    return OolerSleepSchedule(nights=nights, seq=data.get("seq", 0))


class OolerCoordinator:
    """Manages the BLE connection lifecycle for an Ooler device."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        address = entry.unique_id
        assert address is not None

        self.hass = hass
        self.address = address
        self.model = entry.data[CONF_MODEL]
        self.client = OolerBLEDevice(model=self.model)
        self.connection_enabled: bool = True

        self._listeners: list[Callable[[], None]] = []
        self._connect_task: asyncio.Task[None] | None = None
        self._unit_synced: bool = False
        self._cached_sleep_schedule: OolerSleepSchedule | None = None
        self._ha_unit: TemperatureUnit = (
            "C" if hass.config.units is METRIC_SYSTEM else "F"
        )
        self._reconnect_delay: float = (
            int(address.replace(":", ""), 16) % 1500 + 500
        ) / 1000

        self._store: Store[dict[str, Any]] = Store(
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}.{address}.schedules",
        )
        self._saved_schedules: dict[str, OolerSleepSchedule] = {}
        self._active_saved_name: str | None = None

    @property
    def is_connected(self) -> bool:
        """Return whether the device is connected."""
        return self.client.is_connected

    @callback
    def async_add_listener(self, update_callback: Callable[[], None]) -> CALLBACK_TYPE:
        """Add a listener for state updates."""
        self._listeners.append(update_callback)

        @callback
        def remove_listener() -> None:
            self._listeners.remove(update_callback)

        return remove_listener

    @callback
    def _async_notify_listeners(self) -> None:
        """Notify all listeners of a state change."""
        for listener in self._listeners:
            listener()

    async def async_start(self) -> list[CALLBACK_TYPE]:
        """Start the coordinator and return cleanup callbacks."""
        cleanups: list[CALLBACK_TYPE] = []

        # Load saved schedules from persistent storage
        await self.async_load_store()

        # Seed BLEDevice from HA cache
        ble_device = async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if ble_device:
            self.client.set_ble_device(ble_device)

        # Register for BLE advertisement callbacks
        cleanups.append(
            async_register_callback(
                self.hass,
                self._async_update_ble,
                {ADDRESS: self.address},
                BluetoothScanningMode.ACTIVE,
            )
        )

        # Register for library state change callbacks
        cleanups.append(self.client.register_callback(self._async_on_state_change))

        # Periodic reconnect timer
        cleanups.append(
            async_track_time_interval(
                self.hass, self._async_reconnect_check, RECONNECT_INTERVAL
            )
        )

        # Periodic poll timer
        cleanups.append(
            async_track_time_interval(self.hass, self._async_poll_check, POLL_INTERVAL)
        )

        # Periodic clock sync timer
        cleanups.append(
            async_track_time_interval(
                self.hass, self._async_clock_sync_check, CLOCK_SYNC_INTERVAL
            )
        )

        # Stop on HA shutdown
        cleanups.append(
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._async_stop)
        )

        return cleanups

    async def async_stop(self) -> None:
        """Disconnect from the device."""
        self.connection_enabled = False
        await self.client.stop()

    async def async_ensure_connected(self) -> None:
        """Ensure the client is connected, raising HomeAssistantError on failure."""
        if self.client.is_connected:
            return
        # If a connect is already in-flight, await it instead of starting another
        if self._connect_task and not self._connect_task.done():
            await self._connect_task
            if self.client.is_connected:
                return
        try:
            await self.client.connect()
        except (BleakError, TimeoutError) as err:
            _LOGGER.warning(
                "Failed to connect to Ooler %s", self.address, exc_info=True
            )
            msg = f"Failed to connect to Ooler {self.address}"
            raise HomeAssistantError(msg) from err
        await self._async_post_connect()

    async def _async_connect(self, *, stagger: bool = False) -> None:
        """Connect to the device, syncing settings on first connect."""
        try:
            if stagger:
                await asyncio.sleep(self._reconnect_delay)
            await self.client.connect()
            if (
                not self._unit_synced
                and self.client.state.temperature_unit != self._ha_unit
            ):
                _LOGGER.debug(
                    "Syncing Ooler temperature unit from %s to %s",
                    self.client.state.temperature_unit,
                    self._ha_unit,
                )
                await self.client.set_temperature_unit(self._ha_unit)
            self._unit_synced = True
            await self._async_post_connect()
        except (BleakError, TimeoutError):
            _LOGGER.warning(
                "Failed to connect to Ooler %s", self.address, exc_info=True
            )

    async def _async_post_connect(self) -> None:
        """Read sleep schedule and sync clock after connecting."""
        try:
            schedule = await self.client.read_sleep_schedule()
            if schedule.nights:
                self._cached_sleep_schedule = schedule
            self._validate_active_saved_name(schedule)
        except (BleakError, TimeoutError):
            _LOGGER.debug(
                "Failed to read sleep schedule from Ooler %s",
                self.address,
                exc_info=True,
            )
        await self._async_sync_clock()
        self._async_notify_listeners()

    def _schedule_connect(self, *, stagger: bool = False) -> None:
        """Schedule a connection attempt if one isn't already running."""
        if self._connect_task and not self._connect_task.done():
            return
        self._connect_task = self.hass.async_create_task(
            self._async_connect(stagger=stagger)
        )

    @callback
    def _async_update_ble(
        self,
        service_info: BluetoothServiceInfoBleak,
        change: BluetoothChange,
    ) -> None:
        """Update from a BLE callback."""
        self.client.set_ble_device(service_info.device)
        if self.connection_enabled and not self.client.is_connected:
            self._schedule_connect()

    @callback
    def _async_on_state_change(self, *_args: object) -> None:
        """Handle library state change callback."""
        if self.connection_enabled and not self.client.is_connected:
            _LOGGER.debug("Ooler %s disconnected, scheduling reconnect", self.address)
            self._schedule_connect(stagger=True)
        self._async_notify_listeners()

    @callback
    def _async_reconnect_check(self, _now: object = None) -> None:
        """Periodically attempt reconnection if disconnected."""
        if self.connection_enabled and not self.client.is_connected:
            fresh_device = async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if fresh_device:
                self.client.set_ble_device(fresh_device)
            _LOGGER.debug("Periodic reconnect attempt for Ooler %s", self.address)
            self._schedule_connect(stagger=True)

    @callback
    def _async_poll_check(self, _now: object = None) -> None:
        """Periodically poll for water level and clean status."""
        if self.connection_enabled and self.client.is_connected:
            self.hass.async_create_task(self._async_poll())

    async def _async_poll(self) -> None:
        """Poll the device for current state."""
        try:
            await self.client.async_poll()
        except (BleakError, TimeoutError):
            _LOGGER.debug(
                "Periodic poll failed for Ooler %s", self.address, exc_info=True
            )

    async def _async_sync_clock(self) -> None:
        """Sync the device clock to HA's timezone."""
        try:
            tz = ZoneInfo(self.hass.config.time_zone)
            await self.client.sync_clock(datetime.now(tz))
        except (BleakError, TimeoutError):
            _LOGGER.debug(
                "Failed to sync clock on Ooler %s", self.address, exc_info=True
            )

    @callback
    def _async_clock_sync_check(self, _now: object = None) -> None:
        """Periodically sync the device clock."""
        if self.connection_enabled and self.client.is_connected:
            self.hass.async_create_task(self._async_sync_clock())

    @property
    def sleep_schedule_active(self) -> bool:
        """Return whether a sleep schedule is active on the device."""
        schedule = self.client.sleep_schedule
        return schedule is not None and bool(schedule.nights)

    @property
    def cached_sleep_schedule(self) -> OolerSleepSchedule | None:
        """Return the cached sleep schedule for re-enabling."""
        return self._cached_sleep_schedule

    async def async_enable_sleep_schedule(self) -> None:
        """Re-enable the cached sleep schedule on the device."""
        if self._cached_sleep_schedule is None:
            msg = "No cached sleep schedule to enable"
            raise HomeAssistantError(msg)
        await self.async_ensure_connected()
        await self.client.set_sleep_schedule(self._cached_sleep_schedule.nights)
        self._async_notify_listeners()

    async def async_disable_sleep_schedule(self) -> None:
        """Disable the sleep schedule on the device, caching it first."""
        if self.sleep_schedule_active:
            self._cached_sleep_schedule = self.client.sleep_schedule
        await self.async_ensure_connected()
        await self.client.clear_sleep_schedule()
        self._active_saved_name = None
        self._async_notify_listeners()

    async def async_write_sleep_schedule(
        self, nights: list[SleepScheduleNight]
    ) -> None:
        """Write a sleep schedule to the device."""
        await self.async_ensure_connected()
        await self.client.set_sleep_schedule(nights)
        self._cached_sleep_schedule = self.client.sleep_schedule
        self._active_saved_name = None
        self._async_notify_listeners()

    # --- Schedule storage ---

    @property
    def saved_schedules(self) -> dict[str, OolerSleepSchedule]:
        """Return the saved schedules dictionary."""
        return self._saved_schedules

    @property
    def active_saved_name(self) -> str | None:
        """Return the name of the currently active saved schedule, if any."""
        return self._active_saved_name

    def _validate_active_saved_name(self, schedule: OolerSleepSchedule) -> None:
        """Clear active_saved_name if the device schedule no longer matches."""
        if self._active_saved_name is None:
            return
        saved = self._saved_schedules.get(self._active_saved_name)
        if saved is None or saved.nights != schedule.nights:
            self._active_saved_name = None

    @property
    def tonight_schedule(self) -> SleepScheduleNight | None:
        """Return the schedule for tonight based on current day of week."""
        schedule = self.client.sleep_schedule
        if schedule is None or not schedule.nights:
            return None
        tz = ZoneInfo(self.hass.config.time_zone)
        today = datetime.now(tz).weekday()  # 0=Monday, 6=Sunday
        for night in schedule.nights:
            if night.day == today:
                return night
        return None

    async def async_load_store(self) -> None:
        """Load saved schedules from persistent storage."""
        data = await self._store.async_load()
        if data is None:
            return
        for name, schedule_data in data.get("schedules", {}).items():
            self._saved_schedules[name] = _deserialize_schedule(schedule_data)

    async def _async_save_store(self) -> None:
        """Persist saved schedules to storage."""
        data: dict[str, Any] = {
            "schedules": {
                name: _serialize_schedule(schedule)
                for name, schedule in self._saved_schedules.items()
            }
        }
        await self._store.async_save(data)

    async def async_save_schedule(self, name: str) -> None:
        """Save the current device schedule with a name."""
        schedule = self.client.sleep_schedule
        if schedule is None or not schedule.nights:
            msg = "No active schedule on device to save"
            raise HomeAssistantError(msg)
        self._saved_schedules[name] = schedule
        self._active_saved_name = name
        await self._async_save_store()
        self._async_notify_listeners()

    async def async_delete_saved_schedule(self, name: str) -> None:
        """Delete a saved schedule by name."""
        if name not in self._saved_schedules:
            msg = f"No saved schedule named '{name}'"
            raise HomeAssistantError(msg)
        del self._saved_schedules[name]
        if self._active_saved_name == name:
            self._active_saved_name = None
        await self._async_save_store()
        self._async_notify_listeners()

    async def async_load_saved_schedule(self, name: str) -> None:
        """Load a saved schedule onto the device."""
        if name not in self._saved_schedules:
            msg = f"No saved schedule named '{name}'"
            raise HomeAssistantError(msg)
        schedule = self._saved_schedules[name]
        await self.async_ensure_connected()
        await self.client.set_sleep_schedule(schedule.nights)
        self._cached_sleep_schedule = self.client.sleep_schedule
        self._active_saved_name = name
        self._async_notify_listeners()

    async def _async_stop(self, _event: Event) -> None:
        """Close the connection on HA shutdown."""
        await self.client.stop()
