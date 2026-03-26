"""Coordinator for the Ooler Sleep System integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING

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
from homeassistant.util.unit_system import METRIC_SYSTEM
from ooler_ble_client import OolerBLEDevice, TemperatureUnit

from .const import _LOGGER, CONF_MODEL

if TYPE_CHECKING:
    from collections.abc import Callable

RECONNECT_INTERVAL = timedelta(seconds=60)
POLL_INTERVAL = timedelta(minutes=5)


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
        self._ha_unit: TemperatureUnit = (
            "C" if hass.config.units is METRIC_SYSTEM else "F"
        )
        self._reconnect_delay: float = (
            (int(address.replace(":", ""), 16) % 1500 + 500) / 1000
        )

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
        cleanups.append(
            self.client.register_callback(self._async_on_state_change)
        )

        # Periodic reconnect timer
        cleanups.append(
            async_track_time_interval(
                self.hass, self._async_reconnect_check, RECONNECT_INTERVAL
            )
        )

        # Periodic poll timer
        cleanups.append(
            async_track_time_interval(
                self.hass, self._async_poll_check, POLL_INTERVAL
            )
        )

        # Stop on HA shutdown
        cleanups.append(
            self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STOP, self._async_stop
            )
        )

        return cleanups

    async def async_stop(self) -> None:
        """Disconnect from the device."""
        await self.client.stop()

    async def async_ensure_connected(self) -> None:
        """Ensure the client is connected, raising HomeAssistantError on failure."""
        if not self.client.is_connected:
            try:
                await self.client.connect()
            except (BleakError, TimeoutError) as err:
                _LOGGER.warning(
                    "Failed to connect to Ooler %s", self.address, exc_info=True
                )
                msg = f"Failed to connect to Ooler {self.address}"
                raise HomeAssistantError(msg) from err

    async def _async_connect(self, *, stagger: bool = False) -> None:
        """Connect to the device, syncing temperature unit on first connect."""
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
        except (BleakError, TimeoutError):
            _LOGGER.warning(
                "Failed to connect to Ooler %s", self.address, exc_info=True
            )

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

    async def _async_stop(self, _event: Event) -> None:
        """Close the connection on HA shutdown."""
        await self.client.stop()
