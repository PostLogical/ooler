"""The Ooler Sleep System integration."""
from __future__ import annotations

from homeassistant.components.bluetooth import (
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
    async_register_callback,
)
from homeassistant.components.bluetooth.match import ADDRESS
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STARTED,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import CALLBACK_TYPE, CoreState, Event, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from ooler_ble_client import OolerBLEDevice

from .const import _LOGGER, CONF_MODEL, DOMAIN
from .models import OolerData

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SENSOR, Platform.SWITCH]

# Reconnect backoff intervals in seconds (30s, 1m, 2m, 5m, 10m)
RECONNECT_BACKOFF = [30, 60, 120, 300, 600]
RECONNECT_STARTUP_DELAY = 30  # Wait for BLE stack to initialise after HA start


def _setup_reconnect(
    hass: HomeAssistant,
    address: str,
    client: OolerBLEDevice,
) -> tuple[CALLBACK_TYPE, CALLBACK_TYPE]:
    """Create reconnect helpers that retry BLE connection with backoff.

    Returns (cancel_reconnect, schedule_reconnect_if_needed) callbacks.
    """
    _reconnect_cancel: CALLBACK_TYPE | None = None
    _reconnect_attempt: int = 0

    async def _async_try_reconnect() -> None:
        """Attempt to reconnect to the Ooler device with backoff."""
        nonlocal _reconnect_cancel, _reconnect_attempt
        _reconnect_cancel = None

        if client.is_connected:
            _reconnect_attempt = 0
            return

        ble_device = async_ble_device_from_address(
            hass, address, connectable=True
        )
        if ble_device is None:
            ble_device = async_ble_device_from_address(
                hass, address, connectable=False
            )

        if ble_device is not None:
            client.set_ble_device(ble_device)
            try:
                await client.connect()
                if client.is_connected:
                    _LOGGER.info(
                        "Reconnected to %s after %d attempt(s)",
                        address,
                        _reconnect_attempt + 1,
                    )
                    _reconnect_attempt = 0
                    return
            except Exception:
                _LOGGER.debug(
                    "Reconnect to %s failed (attempt %d)",
                    address,
                    _reconnect_attempt + 1,
                    exc_info=True,
                )
        else:
            _LOGGER.debug(
                "No BLE device found for %s (attempt %d)",
                address,
                _reconnect_attempt + 1,
            )

        # Schedule next retry with capped exponential backoff
        _reconnect_attempt += 1
        delay = RECONNECT_BACKOFF[
            min(_reconnect_attempt - 1, len(RECONNECT_BACKOFF) - 1)
        ]
        _LOGGER.debug(
            "Will retry %s in %ds (attempt %d)", address, delay, _reconnect_attempt
        )
        _reconnect_cancel = async_call_later(
            hass,
            delay,
            lambda _now: hass.async_create_task(_async_try_reconnect()),
        )

    @callback
    def cancel_reconnect() -> None:
        """Cancel any pending reconnect timer."""
        nonlocal _reconnect_cancel
        if _reconnect_cancel is not None:
            _reconnect_cancel()
            _reconnect_cancel = None

    @callback
    def schedule_reconnect_if_needed() -> None:
        """Start the reconnect loop if the client is not connected."""
        nonlocal _reconnect_cancel
        if not client.is_connected and _reconnect_cancel is None:
            _reconnect_cancel = async_call_later(
                hass,
                RECONNECT_STARTUP_DELAY,
                lambda _now: hass.async_create_task(_async_try_reconnect()),
            )

    return cancel_reconnect, schedule_reconnect_if_needed


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
    def _async_update_ble_passive(
        service_info: BluetoothServiceInfoBleak,
        change: BluetoothChange,
    ) -> None:
        """Update BLE device reference from passive sources (e.g. Shelly).

        Only updates the device reference for tracking; does NOT attempt
        to connect since passive sources can't relay BLE connections.
        """
        if not hasattr(client, "_ble_device"):
            _LOGGER.debug(
                "Passive BLE update seeding device for %s from %s",
                service_info.address,
                service_info.source,
            )
            client.set_ble_device(service_info.device)

    cancel_reconnect, schedule_reconnect_if_needed = _setup_reconnect(
        hass, address, client
    )

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
        cancel_reconnect()  # BLE stack found us — no need for timer
        client.set_ble_device(service_info.device)
        hass.async_create_task(client.connect())

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

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = OolerData(
        address,
        model,
        client,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # After HA is fully started, kick off reconnect if BLE callbacks haven't
    # already connected us.
    if hass.state is CoreState.running:
        schedule_reconnect_if_needed()
    else:
        entry.async_on_unload(
            hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED,
                lambda _event: schedule_reconnect_if_needed(),
            )
        )

    async def _async_stop(event: Event) -> None:
        """Close the connection."""
        cancel_reconnect()
        await client.stop()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)
    )
    entry.async_on_unload(cancel_reconnect)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
