"""Support for Ooler Sleep System switches."""

from __future__ import annotations

from typing import Any, override

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from ooler_ble_client import DeviceOffError

from . import OolerConfigEntry
from .const import DOMAIN
from .coordinator import OolerCoordinator
from .entity import OolerEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: OolerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Ooler switches."""
    coordinator = config_entry.runtime_data
    async_add_entities(
        [
            OolerDeepCleanSwitch(coordinator),
            OolerSleepScheduleSwitch(coordinator),
            OolerConnectionSwitch(coordinator),
        ]
    )


class OolerDeepCleanSwitch(OolerEntity, SwitchEntity):
    """Representation of Ooler Deep Clean switch."""

    _attr_translation_key = "deep_clean"

    def __init__(self, coordinator: OolerCoordinator) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator)
        # Unchanged from when this entity was named "Cleaning": a new unique_id
        # would orphan every existing entity, losing its history and breaking
        # dashboards and automations that reference it.
        self._attr_unique_id = f"{coordinator.address}_cleaning_binary_sensor"

    @property
    @override
    def is_on(self) -> bool | None:
        """
        Return true if a deep clean is running.

        Tracks deep_clean, not the raw CLEAN characteristic: the device also
        asserts that bit for its own hourly UV water-treatment cycle, which
        nobody can start or stop.
        """
        return self.coordinator.client.state.deep_clean

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start a deep clean, powering the unit on if it is off."""
        await self.coordinator.async_ensure_connected()
        await self.coordinator.client.set_deep_clean(True)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Cancel a running deep clean."""
        await self.coordinator.async_ensure_connected()
        try:
            await self.coordinator.client.set_deep_clean(False)
        except DeviceOffError as err:
            self._resync_after_refusal()
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="set_deep_clean_while_off",
            ) from err


class OolerSleepScheduleSwitch(OolerEntity, SwitchEntity):
    """Representation of Ooler sleep schedule toggle."""

    _attr_translation_key = "sleep_schedule"

    def __init__(self, coordinator: OolerCoordinator) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_sleep_schedule"

    @property
    @override
    def available(self) -> bool:
        """
        Return whether the switch is available.

        Unavailable when disconnected or when there is no schedule to toggle
        (no active schedule and no cached schedule to re-enable).
        """
        if not self.coordinator.is_connected:
            return False
        return (
            self.coordinator.sleep_schedule_active
            or self.coordinator.cached_sleep_schedule is not None
        )

    @property
    @override
    def is_on(self) -> bool:
        """Return true if a sleep schedule is active on the device."""
        return self.coordinator.sleep_schedule_active

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the cached sleep schedule on the device."""
        await self.coordinator.async_enable_sleep_schedule()

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the sleep schedule on the device."""
        await self.coordinator.async_disable_sleep_schedule()


class OolerConnectionSwitch(OolerEntity, SwitchEntity):
    """Representation of Ooler bluetooth connection switch."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "bluetooth_connection"

    def __init__(self, coordinator: OolerCoordinator) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_connection_binary_sensor"

    @property
    @override
    def available(self) -> bool:
        """This switch controls availability, so always return true."""
        return True

    @property
    @override
    def is_on(self) -> bool:
        """Return true if the device is connected."""
        return self.coordinator.client.is_connected

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Connect to the device."""
        self.coordinator.connection_enabled = True
        await self.coordinator.async_ensure_connected()

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disconnect from the device and suppress auto-reconnect."""
        self.coordinator.connection_enabled = False
        if self.coordinator.client.is_connected:
            await self.coordinator.client.stop()
