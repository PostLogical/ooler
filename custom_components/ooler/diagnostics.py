"""Diagnostics support for the Ooler integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import OolerConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: OolerConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    client = coordinator.client
    state = client.state

    return {
        "config_entry": {
            "unique_id": entry.unique_id,
            "data": dict(entry.data),
        },
        "connection": {
            "is_connected": client.is_connected,
            "connection_enabled": coordinator.connection_enabled,
        },
        "device_state": {
            "power": state.power,
            "mode": state.mode,
            "set_temperature": state.set_temperature,
            "actual_temperature": state.actual_temperature,
            "temperature_unit": state.temperature_unit,
            "water_level": state.water_level,
            "clean": state.clean,
        },
    }
