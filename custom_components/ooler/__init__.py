"""The Ooler Sleep System integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import OolerCoordinator
from .services import async_register_services, async_unregister_services

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

type OolerConfigEntry = ConfigEntry[OolerCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: OolerConfigEntry) -> bool:
    """Set up Ooler from a config entry."""
    coordinator = OolerCoordinator(hass, entry)
    cleanups = await coordinator.async_start()
    for cleanup in cleanups:
        entry.async_on_unload(cleanup)

    entry.runtime_data = coordinator

    async_register_services(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OolerConfigEntry) -> bool:
    """Unload a config entry."""
    await entry.runtime_data.async_stop()
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Only unregister services if this is the last Ooler config entry
    if unloaded:
        remaining = [
            e
            for e in hass.config_entries.async_entries("ooler")
            if e.entry_id != entry.entry_id
        ]
        if not remaining:
            async_unregister_services(hass)

    return unloaded
