"""The Ooler Sleep System integration."""
from __future__ import annotations

from homeassistant.components.bluetooth import (
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
    async_register_callback,
    async_track_unavailable,
)
from homeassistant.components.bluetooth.match import ADDRESS, BluetoothCallbackMatcher
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import CoreState, Event, HomeAssistant, callback
from ooler_ble_client import OolerBLEDevice

from .const import _LOGGER, CONF_MODEL, DOMAIN
from .models import OolerData

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SENSOR, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Ooler from a config entry."""
    address = entry.unique_id
    assert address is not None

    model = entry.data[CONF_MODEL]
    client = OolerBLEDevice(model=model)

    # Seed the BLE device immediately so it's available before callbacks fire
    ble_device = async_ble_device_from_address(hass, address, connectable=True)
    if ble_device is None:
        ble_device = async_ble_device_from_address(hass, address, connectable=False)
    if ble_device is not None:
        _LOGGER.debug("Seeding BLE device for %s from %s", address, ble_device.name)
        client.set_ble_device(ble_device)

    @callback
    def _async_update_ble_connectable(
        service_info: BluetoothServiceInfoBleak,
        change: BluetoothChange,
    ) -> None:
        """Update from a connectable BLE source and connect."""
        _LOGGER.debug(
            "Connectable BLE update for %s from %s",
            service_info.address,
            service_info.source,
        )
        client.set_ble_device(service_info.device)
        hass.async_create_task(client.connect())

    @callback
    def _async_update_ble_passive(
        service_info: BluetoothServiceInfoBleak,
        change: BluetoothChange,
    ) -> None:
        """Update BLE device reference from passive sources (e.g. Shelly).

        Only updates the device reference for tracking; does NOT attempt
        to connect since passive sources can't relay BLE connections.
        """
        if not hasattr(client, '_ble_device'):
            _LOGGER.debug(
                "Passive BLE update seeding device for %s from %s",
                service_info.address,
                service_info.source,
            )
            client.set_ble_device(service_info.device)

    # Register for connectable callbacks — these trigger connection
    entry.async_on_unload(
        async_register_callback(
            hass,
            _async_update_ble_connectable,
            {ADDRESS: address},
            BluetoothScanningMode.ACTIVE,
        )
    )

    # Register for passive callbacks — only seeds the device reference
    # so that _ble_device exists even when only Shelly proxies see the device
    entry.async_on_unload(
        async_register_callback(
            hass,
            _async_update_ble_passive,
            {ADDRESS: address},
            BluetoothScanningMode.PASSIVE,
        )
    )

    # def _unavailable_callback(info: BluetoothServiceInfoBleak) -> None:
    #     _LOGGER.error("%s is no longer seen", info.address)
    #     hass.async_create_task(client.connect())

    # entry.async_on_unload(
    #     async_track_unavailable(hass, _unavailable_callback, address, connectable=True)
    # )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = OolerData(
        address,
        model,
        client,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _async_stop(event: Event) -> None:
        """Close the connection."""
        await client.stop()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
