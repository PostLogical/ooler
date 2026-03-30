"""Config flow for Ooler Sleep System integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection
from ooler_ble_client import OolerBLEDevice
from ooler_ble_client.const import POWER_CHAR
import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
    async_discovered_service_info,
    async_last_service_info,
)
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_MODEL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class OolerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Ooler."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, str] = {}
        self._pairing_task: asyncio.Task | None = None
        self._paired: bool = False
        self._bledevice: BLEDevice | None = None
        self._client: OolerBLEDevice | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle the bluetooth discovery step."""
        _LOGGER.debug(
            "async_step_bluetooth: name=%s address=%s connectable=%s source=%s",
            discovery_info.name,
            discovery_info.address,
            discovery_info.connectable,
            discovery_info.source,
        )
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        if not discovery_info.name.startswith("OOLER"):
            return self.async_abort(reason="not_supported")
        self._discovery_info = discovery_info
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm discovery."""
        assert self._discovery_info is not None
        discovery_info = self._discovery_info

        model_name = discovery_info.name
        assert model_name is not None
        _LOGGER.debug("async_step_bluetooth_confirm: model=%s user_input=%s", model_name, user_input)

        if user_input is not None:
            if not self._paired:
                return await self.async_step_wait_for_pairing_mode()
            return self._create_ooler_entry(model_name)

        self._set_confirm_only()
        placeholders = {"name": model_name}
        self.context["title_placeholders"] = placeholders
        return self.async_show_form(
            step_id="bluetooth_confirm", description_placeholders=placeholders
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user step to pick discovered device."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            _LOGGER.debug("async_step_user: selected address=%s", address)

            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()

            model_name = self._discovered_devices[address]
            if model_name is None:
                _LOGGER.debug("async_step_user: model_name is None, aborting")
                return self.async_abort(reason="no_devices_found")

            discovery_info = async_last_service_info(
                self.hass, address, connectable=True
            )
            _LOGGER.debug(
                "async_step_user: async_last_service_info(connectable=True) = %s",
                discovery_info,
            )
            if discovery_info is None:
                discovery_info = async_last_service_info(
                    self.hass, address, connectable=False
                )
                _LOGGER.debug(
                    "async_step_user: async_last_service_info(connectable=False) = %s",
                    discovery_info,
                )
            if discovery_info is None:
                _LOGGER.debug("async_step_user: no service info at all, aborting")
                return self.async_abort(reason="no_devices_found")

            _LOGGER.debug(
                "async_step_user: using discovery name=%s address=%s connectable=%s source=%s",
                discovery_info.name,
                discovery_info.address,
                discovery_info.connectable,
                discovery_info.source,
            )
            self._discovery_info = discovery_info

            if not self._paired:
                _LOGGER.debug("async_step_user: not paired, entering wait_for_pairing_mode")
                return await self.async_step_wait_for_pairing_mode()
            return self._create_ooler_entry(model_name)

        configured_addresses = self._async_current_ids()
        for discovery_info in async_discovered_service_info(self.hass, False):
            address = discovery_info.address
            if (
                address in configured_addresses
                or address in self._discovered_devices
                or not discovery_info.name.startswith("OOLER")
            ):
                continue
            _LOGGER.debug(
                "async_step_user: discovered %s at %s (connectable=%s, source=%s)",
                discovery_info.name,
                address,
                discovery_info.connectable,
                discovery_info.source,
            )
            self._discovered_devices[address] = discovery_info.name

        if not self._discovered_devices:
            _LOGGER.debug("async_step_user: no OOLER devices discovered")
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_ADDRESS): vol.In(self._discovered_devices)}
            ),
        )

    async def async_step_wait_for_pairing_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Wait for device to enter pairing mode."""
        _LOGGER.debug(
            "wait_for_pairing: _pairing_task=%s has_discovery_info=%s",
            self._pairing_task,
            self._discovery_info is not None,
        )
        if not self._pairing_task:
            discovery_info = self._discovery_info
            if discovery_info is None:
                _LOGGER.debug("wait_for_pairing: discovery_info is None, showing timeout")
                return self.async_show_progress_done(next_step_id="pairing_timeout")
            bledevice = discovery_info.device
            _LOGGER.debug(
                "wait_for_pairing: creating connection test task for %s (%s)",
                bledevice.name,
                bledevice.address,
            )
            self._pairing_task = self.hass.async_create_task(
                self._async_check_ooler_connection(bledevice)
            )
            return self.async_show_progress(
                step_id="wait_for_pairing_mode",
                progress_action="wait_for_pairing_mode",
            )
        _LOGGER.debug("wait_for_pairing: awaiting existing pairing task")
        try:
            await self._pairing_task
        except asyncio.CancelledError:
            _LOGGER.debug("wait_for_pairing: task was CANCELLED (connection test failed)")
            self._pairing_task = None
            return self.async_show_progress_done(next_step_id="pairing_timeout")
        _LOGGER.debug("wait_for_pairing: task completed SUCCESSFULLY")
        self._pairing_task = None
        return self.async_show_progress_done(next_step_id="pairing_complete")

    async def async_step_pairing_complete(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Create a configuration entry for a device that entered pairing mode."""
        assert self._discovery_info
        model_name = self._discovery_info.name
        _LOGGER.debug("pairing_complete: creating entry for %s", model_name)

        await self.async_set_unique_id(
            self._discovery_info.address, raise_on_progress=False
        )
        self._abort_if_unique_id_configured()

        return self._create_ooler_entry(model_name)

    async def async_step_pairing_timeout(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Inform the user that the device never entered pairing mode."""
        _LOGGER.debug("pairing_timeout: user_input=%s", user_input)
        if user_input is not None:
            return await self.async_step_wait_for_pairing_mode()

        self._set_confirm_only()
        return self.async_show_form(step_id="pairing_timeout")

    def _create_ooler_entry(self, model_name: str) -> FlowResult:
        return self.async_create_entry(
            title=model_name,
            data={CONF_MODEL: model_name},
        )

    async def _async_check_ooler_connection(self, bledevice: BLEDevice) -> None:
        """Try to connect and test read/write to verify device is paired."""
        _LOGGER.debug(
            "_async_check: starting, will sleep 5s then test %s (%s)",
            bledevice.name,
            bledevice.address,
        )
        await asyncio.sleep(5)
        assert self._pairing_task is not None
        try:
            _LOGGER.debug("_async_check: calling _test_connection_via_proxy (timeout=30s)")
            await asyncio.wait_for(
                self._test_connection_via_proxy(bledevice), timeout=30
            )
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.debug(
                "_async_check: connection test FAILED: %s: %s",
                type(err).__name__,
                err,
            )
            self._pairing_task.cancel()
        else:
            _LOGGER.debug("_async_check: connection test PASSED, device is paired")
            self._paired = True
        finally:
            _LOGGER.debug("_async_check: reconfiguring flow")
            try:
                self.hass.async_create_task(
                    self.hass.config_entries.flow.async_configure(
                        flow_id=self.flow_id
                    )
                )
            except Exception:  # pylint: disable=broad-except
                _LOGGER.debug("_async_check: flow already dismissed, ignoring")

    async def _test_connection_via_proxy(self, bledevice: BLEDevice) -> bool:
        """Test connection using establish_connection for reliable proxy support."""
        # Try to get a connectable BLEDevice from a proxy that supports active connections
        connectable_device = async_ble_device_from_address(
            self.hass, bledevice.address, connectable=True
        )
        if connectable_device:
            _LOGGER.debug(
                "_test_conn: got connectable BLEDevice from proxy for %s (%s)",
                connectable_device.name,
                connectable_device.address,
            )
            target = connectable_device
        else:
            _LOGGER.debug(
                "_test_conn: no connectable proxy found, falling back to %s (%s)",
                bledevice.name,
                bledevice.address,
            )
            target = bledevice

        _LOGGER.debug("_test_conn: establishing connection")
        client = await establish_connection(
            BleakClient,
            target,
            target.name or target.address,
        )
        _LOGGER.debug("_test_conn: connected, is_connected=%s", client.is_connected)
        try:
            _LOGGER.debug("_test_conn: reading POWER_CHAR (%s)", POWER_CHAR)
            orig_power_byte = await client.read_gatt_char(POWER_CHAR)
            orig_power = bool(int.from_bytes(orig_power_byte, "little"))
            _LOGGER.debug(
                "_test_conn: current power=%s (raw=%s)", orig_power, orig_power_byte.hex()
            )

            write_power_byte = int(not orig_power).to_bytes(1, "little")
            _LOGGER.debug(
                "_test_conn: writing power=%s (raw=%s)",
                not orig_power,
                write_power_byte.hex(),
            )
            await client.write_gatt_char(POWER_CHAR, write_power_byte, True)
            _LOGGER.debug("_test_conn: write OK, sleeping 1s before verify")

            await asyncio.sleep(1)

            read_power_byte = await client.read_gatt_char(POWER_CHAR)
            _LOGGER.debug(
                "_test_conn: verify read=%s (expected=%s)",
                read_power_byte.hex(),
                write_power_byte.hex(),
            )

            if write_power_byte == read_power_byte:
                _LOGGER.debug("_test_conn: VERIFIED OK - restoring original power state")
                await client.write_gatt_char(POWER_CHAR, orig_power_byte, True)
                _LOGGER.debug("_test_conn: SUCCESS - pairing confirmed")
                return True
            else:
                _LOGGER.debug(
                    "_test_conn: VERIFY FAILED - wrote %s but read %s",
                    write_power_byte.hex(),
                    read_power_byte.hex(),
                )
                raise RuntimeError(
                    f"Power write-back verification failed: wrote {write_power_byte.hex()}, "
                    f"read {read_power_byte.hex()}"
                )
        finally:
            _LOGGER.debug("_test_conn: disconnecting")
            await client.disconnect()
