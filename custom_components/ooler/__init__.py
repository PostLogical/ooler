"""The Ooler Sleep System integration."""

from __future__ import annotations

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
from homeassistant.util.unit_system import METRIC_SYSTEM
from ooler_ble_client import OolerBLEDevice

from .const import CONF_MODEL, _LOGGER
from .models import OolerData

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SENSOR, Platform.SWITCH]

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

    async def _async_connect_and_sync_unit() -> None:
        """Connect and sync temperature unit to match HA."""
        try:
            await client.connect()
            if client.state.temperature_unit != ha_unit:
                _LOGGER.debug(
                    "Syncing Ooler temperature unit from %s to %s",
                    client.state.temperature_unit,
                    ha_unit,
                )
                await client.set_temperature_unit(ha_unit)
        except Exception:
            _LOGGER.debug(
                "Failed to connect to Ooler %s", address, exc_info=True
            )

    data = OolerData(address, model, client)

    @callback
    def _async_update_ble(
        service_info: BluetoothServiceInfoBleak,
        change: BluetoothChange,
    ) -> None:
        """Update from a ble callback."""
        client.set_ble_device(service_info.device)
        if data.connection_enabled and not client.is_connected:
            hass.async_create_task(_async_connect_and_sync_unit())

    entry.async_on_unload(
        async_register_callback(
            hass,
            _async_update_ble,
            {ADDRESS: address},
            BluetoothScanningMode.ACTIVE,
        )
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
