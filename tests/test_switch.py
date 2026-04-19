"""Tests for the Ooler switch entities."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant

from custom_components.ooler.coordinator import OolerCoordinator
from custom_components.ooler.switch import (
    OolerCleaningSwitch,
    OolerConnectionSwitch,
    OolerSleepScheduleSwitch,
    async_setup_entry,
)

from .conftest import OOLER_ADDRESS, OOLER_NAME, make_mock_client, make_mock_schedule


def make_coordinator_with_client(client: MagicMock) -> OolerCoordinator:
    """Create a coordinator with a mocked client."""
    coordinator = MagicMock(spec=OolerCoordinator)
    coordinator.address = OOLER_ADDRESS
    coordinator.model = OOLER_NAME
    coordinator.client = client
    coordinator.is_connected = client.is_connected
    coordinator.connection_enabled = True
    return coordinator


async def test_async_setup_entry() -> None:
    """Test platform setup creates both switch entities."""
    hass = MagicMock(spec=HomeAssistant)
    coordinator = MagicMock(spec=OolerCoordinator)
    coordinator.address = OOLER_ADDRESS
    coordinator.model = OOLER_NAME
    coordinator.client = make_mock_client()

    entry = MagicMock()
    entry.runtime_data = coordinator

    added_entities: list = []

    def mock_add_entities(entities: list) -> None:
        added_entities.extend(entities)

    await async_setup_entry(hass, entry, mock_add_entities)

    assert len(added_entities) == 3
    assert isinstance(added_entities[0], OolerCleaningSwitch)
    assert isinstance(added_entities[1], OolerSleepScheduleSwitch)
    assert isinstance(added_entities[2], OolerConnectionSwitch)


class TestOolerCleaningSwitch:
    """Tests for the cleaning switch."""

    def _make_entity(self, *, connected: bool = True) -> OolerCleaningSwitch:
        client = make_mock_client(connected=connected)
        coordinator = make_coordinator_with_client(client)
        return OolerCleaningSwitch(coordinator)

    def test_unique_id(self) -> None:
        """Test unique ID format."""
        entity = self._make_entity()
        assert entity.unique_id == f"{OOLER_ADDRESS}_cleaning_binary_sensor"

    def test_translation_key(self) -> None:
        """Test entity translation key."""
        entity = self._make_entity()
        assert entity.translation_key == "cleaning"

    def test_is_on(self) -> None:
        """Test is_on reflects clean state."""
        entity = self._make_entity()
        entity.coordinator.client.state.clean = True
        assert entity.is_on is True

        entity.coordinator.client.state.clean = False
        assert entity.is_on is False

    def test_is_on_state_none(self) -> None:
        """Test is_on returns None when state is None."""
        entity = self._make_entity()
        entity.coordinator.client.state = None
        assert entity.is_on is None

    def test_available(self) -> None:
        """Test availability."""
        entity = self._make_entity(connected=True)
        assert entity.available is True

        entity = self._make_entity(connected=False)
        assert entity.available is False

    async def test_turn_on(self) -> None:
        """Test turning on the cleaning switch."""
        entity = self._make_entity()
        await entity.async_turn_on()
        entity.coordinator.client.set_clean.assert_called_once_with(True)

    async def test_turn_off(self) -> None:
        """Test turning off the cleaning switch."""
        entity = self._make_entity()
        await entity.async_turn_off()
        entity.coordinator.client.set_clean.assert_called_once_with(False)


class TestOolerSleepScheduleSwitch:
    """Tests for the sleep schedule switch."""

    def _make_entity(
        self, *, connected: bool = True, schedule_active: bool = False
    ) -> OolerSleepScheduleSwitch:
        client = make_mock_client(connected=connected)
        coordinator = make_coordinator_with_client(client)
        coordinator.sleep_schedule_active = schedule_active
        coordinator.cached_sleep_schedule = None
        return OolerSleepScheduleSwitch(coordinator)

    def test_unique_id(self) -> None:
        """Test unique ID format."""
        entity = self._make_entity()
        assert entity.unique_id == f"{OOLER_ADDRESS}_sleep_schedule"

    def test_translation_key(self) -> None:
        """Test entity translation key."""
        entity = self._make_entity()
        assert entity.translation_key == "sleep_schedule"

    def test_is_on_active(self) -> None:
        """Test is_on when schedule is active."""
        entity = self._make_entity(schedule_active=True)
        assert entity.is_on is True

    def test_is_on_inactive(self) -> None:
        """Test is_on when schedule is inactive."""
        entity = self._make_entity(schedule_active=False)
        assert entity.is_on is False

    def test_available_no_cache(self) -> None:
        """Test switch unavailable when no cached schedule and not active."""
        entity = self._make_entity(schedule_active=False)
        entity.coordinator.cached_sleep_schedule = None
        assert entity.available is False

    def test_available_with_cache(self) -> None:
        """Test switch available when cached schedule exists."""
        entity = self._make_entity(connected=True)
        entity.coordinator.cached_sleep_schedule = make_mock_schedule()
        assert entity.available is True

    def test_available_when_active(self) -> None:
        """Test switch available when schedule is active."""
        entity = self._make_entity(connected=True, schedule_active=True)
        assert entity.available is True

    def test_available_when_disconnected(self) -> None:
        """Test switch unavailable when disconnected."""
        entity = self._make_entity(connected=False)
        entity.coordinator.cached_sleep_schedule = make_mock_schedule()
        assert entity.available is False

    async def test_turn_on(self) -> None:
        """Test turning on enables the sleep schedule."""
        entity = self._make_entity()
        await entity.async_turn_on()
        entity.coordinator.async_enable_sleep_schedule.assert_called_once()

    async def test_turn_off(self) -> None:
        """Test turning off disables the sleep schedule."""
        entity = self._make_entity()
        await entity.async_turn_off()
        entity.coordinator.async_disable_sleep_schedule.assert_called_once()


class TestOolerConnectionSwitch:
    """Tests for the connection switch."""

    def _make_entity(self, *, connected: bool = True) -> OolerConnectionSwitch:
        client = make_mock_client(connected=connected)
        coordinator = make_coordinator_with_client(client)
        return OolerConnectionSwitch(coordinator)

    def test_unique_id(self) -> None:
        """Test unique ID format."""
        entity = self._make_entity()
        assert entity.unique_id == f"{OOLER_ADDRESS}_connection_binary_sensor"

    def test_always_available(self) -> None:
        """Test connection switch is always available."""
        entity = self._make_entity(connected=False)
        assert entity.available is True

    def test_is_on_connected(self) -> None:
        """Test is_on when connected."""
        entity = self._make_entity(connected=True)
        assert entity.is_on is True

    def test_is_on_disconnected(self) -> None:
        """Test is_on when disconnected."""
        entity = self._make_entity(connected=False)
        assert entity.is_on is False

    async def test_turn_on(self) -> None:
        """Test turning on enables connection."""
        entity = self._make_entity(connected=False)
        await entity.async_turn_on()
        assert entity.coordinator.connection_enabled is True
        entity.coordinator.async_ensure_connected.assert_called_once()

    async def test_turn_off(self) -> None:
        """Test turning off disables connection."""
        entity = self._make_entity(connected=True)
        await entity.async_turn_off()
        assert entity.coordinator.connection_enabled is False
        entity.coordinator.client.stop.assert_called_once()

    def test_entity_category(self) -> None:
        """Test connection switch is categorized as diagnostic."""
        entity = self._make_entity()
        assert entity.entity_category == EntityCategory.DIAGNOSTIC
