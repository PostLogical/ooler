"""Support for Ooler Sleep System select entities."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OolerConfigEntry
from .coordinator import OolerCoordinator
from .entity import OolerEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: OolerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Ooler select entities."""
    coordinator = config_entry.runtime_data
    async_add_entities([OolerSavedScheduleSelect(coordinator)])


class OolerSavedScheduleSelect(OolerEntity, SelectEntity):
    """Select entity for choosing between saved sleep schedules."""

    _attr_translation_key = "saved_schedule"

    def __init__(self, coordinator: OolerCoordinator) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._attr_name = "Saved Schedule"
        self._attr_unique_id = f"{coordinator.address}_saved_schedule"

    @property
    def available(self) -> bool:
        """Available when connected and schedules exist."""
        return (
            self.coordinator.is_connected
            and bool(self.coordinator.saved_schedules)
        )

    @property
    def options(self) -> list[str]:
        """Return the list of saved schedule names."""
        names = list(self.coordinator.saved_schedules.keys())
        return names or ["(none)"]

    @property
    def current_option(self) -> str | None:
        """Return the currently active saved schedule name."""
        return self.coordinator.active_saved_name

    async def async_select_option(self, option: str) -> None:
        """Load the selected schedule onto the device."""
        await self.coordinator.async_load_saved_schedule(option)
