"""The Ooler Sleep System integration."""

from __future__ import annotations

from homeassistant.components.bluetooth import (
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
    async_register_callback,
)
from homeassistant.components.bluetooth.match import ADDRESS
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant, callback
from ooler_ble_client import OolerBLEDevice

from .const import CONF_MODEL
from .models import OolerData

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SENSOR, Platform.SWITCH]

type OolerConfigEntry = ConfigEntry[OolerData]


async def async_setup_entry(hass: HomeAssistant, entry: OolerConfigEntry) -> bool:
    """Set up Ooler from a config entry."""
    address = entry.unique_id
    assert address is not None

    model = entry.data[CONF_MODEL]
    client = OolerBLEDevice(model=model)

    @callback
    def _async_update_ble(
        service_info: BluetoothServiceInfoBleak,
        change: BluetoothChange,
    ) -> None:
        """Update from a ble callback."""
        client.set_ble_device(service_info.device)
        if not client.is_connected:
            hass.async_create_task(client.connect())

    entry.async_on_unload(
        async_register_callback(
            hass,
            _async_update_ble,
            {ADDRESS: address},
            BluetoothScanningMode.ACTIVE,
        )
    )

    entry.runtime_data = OolerData(address, model, client)

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
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
