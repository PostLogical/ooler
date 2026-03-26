"""Config flow for Ooler Sleep System integration."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol
from bleak.exc import BleakError
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
    async_last_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS
from ooler_ble_client import OolerBLEDevice

from .const import _LOGGER, CONF_MODEL, DOMAIN


class OolerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Ooler."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, str] = {}
        self._pairing_task: asyncio.Task[None] | None = None
        self._paired: bool = False

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle the bluetooth discovery step."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        if not discovery_info.name.startswith("OOLER"):
            return self.async_abort(reason="not_supported")
        self._discovery_info = discovery_info
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery."""
        assert self._discovery_info is not None
        discovery_info = self._discovery_info

        model_name = discovery_info.name
        assert model_name is not None

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
    ) -> ConfigFlowResult:
        """Handle the user step to pick discovered device."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]

            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()

            model_name = self._discovered_devices[address]
            if model_name is None:
                return self.async_abort(reason="no_devices_found")

            discovery_info = async_last_service_info(
                self.hass, address, connectable=True
            )
            self._discovery_info = discovery_info

            if not self._paired:
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
            self._discovered_devices[address] = discovery_info.name

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_ADDRESS): vol.In(self._discovered_devices)}
            ),
        )

    async def async_step_wait_for_pairing_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Verify BLE connection to the device."""
        if not self._pairing_task:
            discovery_info = self._discovery_info
            if discovery_info is None:
                return self.async_show_progress_done(next_step_id="pairing_timeout")
            self._pairing_task = self.hass.async_create_task(
                self._async_verify_connection(discovery_info)
            )
            return self.async_show_progress(
                step_id="wait_for_pairing_mode",
                progress_action="wait_for_pairing_mode",
                progress_task=self._pairing_task,
            )
        try:
            await self._pairing_task
        except asyncio.CancelledError:
            self._pairing_task = None
            return self.async_show_progress_done(next_step_id="pairing_timeout")
        self._pairing_task = None
        if not self._paired:
            return self.async_show_progress_done(next_step_id="pairing_timeout")
        return self.async_show_progress_done(next_step_id="pairing_complete")

    async def async_step_pairing_complete(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create a configuration entry for a device that entered pairing mode."""
        assert self._discovery_info
        model_name = self._discovery_info.name

        await self.async_set_unique_id(
            self._discovery_info.address, raise_on_progress=False
        )
        self._abort_if_unique_id_configured()

        return self._create_ooler_entry(model_name)

    async def async_step_pairing_timeout(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Inform the user that the device never entered pairing mode."""
        if user_input is not None:
            self._pairing_task = None
            return await self.async_step_wait_for_pairing_mode()

        self._set_confirm_only()
        return self.async_show_form(step_id="pairing_timeout")

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration to re-verify the BLE connection."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert entry is not None

        if user_input is not None:
            address = entry.unique_id
            assert address is not None
            discovery_info = async_last_service_info(
                self.hass, address, connectable=True
            )
            if discovery_info is None:
                return self.async_abort(reason="no_devices_found")
            self._discovery_info = discovery_info
            return await self.async_step_wait_for_pairing_mode()

        return self.async_show_form(step_id="reconfigure")

    def _create_ooler_entry(self, model_name: str) -> ConfigFlowResult:
        return self.async_create_entry(
            title=model_name,
            data={CONF_MODEL: model_name},
        )

    async def _async_verify_connection(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> None:
        """Connect to the device and verify GATT access by reading state."""
        client = OolerBLEDevice(model=discovery_info.name)
        client.set_ble_device(discovery_info.device)
        try:
            await client.connect()
            await client.async_poll()
            self._paired = True
            _LOGGER.debug(
                "Connection verified for %s", discovery_info.address
            )
        except (BleakError, TimeoutError):
            _LOGGER.debug(
                "Connection verification failed for %s",
                discovery_info.address,
                exc_info=True,
            )
        finally:
            await client.stop()
