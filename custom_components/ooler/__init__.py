"""The Ooler Sleep System integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from homeassistant.components.bluetooth import (
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
    async_last_service_info,
    async_register_callback,
)
from homeassistant.components.bluetooth.match import ADDRESS
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util.unit_system import METRIC_SYSTEM
from ooler_ble_client import OolerBLEDevice

from .const import CONF_MODEL, _LOGGER
from .models import OolerData

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SENSOR, Platform.SWITCH]

RECONNECT_INTERVAL = timedelta(seconds=60)
POLL_INTERVAL = timedelta(minutes=5)

type OolerConfigEntry = ConfigEntry[OolerData]


async def async_setup_entry(hass: HomeAssistant, entry: OolerConfigEntry) -> bool:
    """Set up Ooler from a config entry."""
    address = entry.unique_id
    assert address is not None

    model = entry.data[CONF_MODEL]
    client = OolerBLEDevice(model=model)

    # Seed the BLEDevice from HA's cache so connect() works immediately
    service_info = async_last_service_info(hass, address, connectable=True)
    if service_info:
        client.set_ble_device(service_info.device)

    ha_unit = "C" if hass.config.units is METRIC_SYSTEM else "F"
    unit_synced = False

    # Stagger reconnects across devices using the address as a seed.
    # This avoids all devices racing for proxy slots simultaneously.
    reconnect_delay = (int(address.replace(":", ""), 16) % 1500 + 500) / 1000

    async def _async_connect(stagger: bool = False) -> None:
        """Connect to the device, syncing temperature unit on first connect."""
        nonlocal unit_synced
        try:
            if stagger:
                await asyncio.sleep(reconnect_delay)
            await client.connect()
            if not unit_synced and client.state.temperature_unit != ha_unit:
                _LOGGER.debug(
                    "Syncing Ooler temperature unit from %s to %s",
                    client.state.temperature_unit,
                    ha_unit,
                )
                await client.set_temperature_unit(ha_unit)
            unit_synced = True
        except Exception:
            _LOGGER.warning(
                "Failed to connect to Ooler %s", address, exc_info=True
            )

    data = OolerData(address, model, client)
    connect_task: asyncio.Task[None] | None = None

    def _schedule_connect(stagger: bool = False) -> None:
        """Schedule a connection attempt if one isn't already running."""
        nonlocal connect_task
        if connect_task and not connect_task.done():
            return
        connect_task = hass.async_create_task(_async_connect(stagger=stagger))

    @callback
    def _async_update_ble(
        service_info: BluetoothServiceInfoBleak,
        change: BluetoothChange,
    ) -> None:
        """Update from a ble callback."""
        client.set_ble_device(service_info.device)
        if data.connection_enabled and not client.is_connected:
            _schedule_connect()

    entry.async_on_unload(
        async_register_callback(
            hass,
            _async_update_ble,
            {ADDRESS: address},
            BluetoothScanningMode.ACTIVE,
        )
    )

    @callback
    def _async_on_state_change(*_args: object) -> None:
        """Trigger immediate reconnect when the device disconnects."""
        if data.connection_enabled and not client.is_connected:
            _LOGGER.debug("Ooler %s disconnected, scheduling reconnect", address)
            _schedule_connect(stagger=True)

    entry.async_on_unload(client.register_callback(_async_on_state_change))

    @callback
    def _async_reconnect_check(_now: object = None) -> None:
        """Periodically attempt reconnection if disconnected."""
        if data.connection_enabled and not client.is_connected:
            fresh_info = async_last_service_info(hass, address, connectable=True)
            if fresh_info:
                client.set_ble_device(fresh_info.device)
            _LOGGER.debug("Periodic reconnect attempt for Ooler %s", address)
            _schedule_connect(stagger=True)

    entry.async_on_unload(
        async_track_time_interval(hass, _async_reconnect_check, RECONNECT_INTERVAL)
    )

    @callback
    def _async_poll_check(_now: object = None) -> None:
        """Periodically poll for water level and clean status."""
        if data.connection_enabled and client.is_connected:
            hass.async_create_task(_async_poll())

    async def _async_poll() -> None:
        """Poll the device for current state."""
        try:
            await client.async_poll()
        except Exception:
            _LOGGER.debug(
                "Periodic poll failed for Ooler %s", address, exc_info=True
            )

    entry.async_on_unload(
        async_track_time_interval(hass, _async_poll_check, POLL_INTERVAL)
    )

    entry.runtime_data = data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _async_stop(event: Event) -> None:
        """Close the connection."""
        await client.stop()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OolerConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.client.stop()
    return unload_ok
