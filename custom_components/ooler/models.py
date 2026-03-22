"""Models for the Ooler Sleep System integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.exceptions import HomeAssistantError
from ooler_ble_client import OolerBLEDevice

from .const import _LOGGER


@dataclass
class OolerData:
    """Data for the Ooler integration."""

    address: str
    model: str
    client: OolerBLEDevice
    connection_enabled: bool = True

    async def async_ensure_connected(self) -> None:
        """Ensure the client is connected, raising HomeAssistantError on failure."""
        if not self.client.is_connected:
            try:
                await self.client.connect()
            except Exception as err:
                _LOGGER.warning(
                    "Failed to connect to Ooler %s", self.address, exc_info=True
                )
                raise HomeAssistantError(
                    f"Failed to connect to Ooler {self.address}"
                ) from err
