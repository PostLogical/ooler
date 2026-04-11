"""Tests for the Ooler select entities."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from homeassistant.core import HomeAssistant

from custom_components.ooler.coordinator import OolerCoordinator
from custom_components.ooler.select import OolerSavedScheduleSelect, async_setup_entry

from .conftest import OOLER_ADDRESS, OOLER_NAME, make_mock_client, make_mock_schedule


def make_coordinator_with_client(client: MagicMock) -> OolerCoordinator:
    """Create a coordinator with a mocked client."""
    coordinator = MagicMock(spec=OolerCoordinator)
    coordinator.address = OOLER_ADDRESS
    coordinator.model = OOLER_NAME
    coordinator.client = client
    coordinator.is_connected = client.is_connected
    return coordinator


async def test_async_setup_entry() -> None:
    """Test platform setup creates select entity."""
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

    assert len(added_entities) == 1
    assert isinstance(added_entities[0], OolerSavedScheduleSelect)


class TestOolerSavedScheduleSelect:
    """Tests for the saved schedule select entity."""

    def _make_entity(
        self,
        *,
        connected: bool = True,
        saved_schedules: dict | None = None,
        active_name: str | None = None,
    ) -> OolerSavedScheduleSelect:
        client = make_mock_client(connected=connected)
        coordinator = make_coordinator_with_client(client)
        coordinator.saved_schedules = saved_schedules or {}
        coordinator.active_saved_name = active_name
        coordinator.async_load_saved_schedule = AsyncMock()
        return OolerSavedScheduleSelect(coordinator)

    def test_unique_id(self) -> None:
        """Test unique ID format."""
        entity = self._make_entity()
        assert entity.unique_id == f"{OOLER_ADDRESS}_saved_schedule"

    def test_name(self) -> None:
        """Test entity name."""
        entity = self._make_entity()
        assert entity.name == "Saved Schedule"

    def test_available_connected_with_schedules(self) -> None:
        """Test available when connected and schedules exist."""
        entity = self._make_entity(
            connected=True,
            saved_schedules={"weekday": make_mock_schedule()},
        )
        assert entity.available is True

    def test_unavailable_disconnected(self) -> None:
        """Test unavailable when disconnected."""
        entity = self._make_entity(
            connected=False,
            saved_schedules={"weekday": make_mock_schedule()},
        )
        assert entity.available is False

    def test_unavailable_no_schedules(self) -> None:
        """Test unavailable when no saved schedules."""
        entity = self._make_entity(connected=True, saved_schedules={})
        assert entity.available is False

    def test_options_with_schedules(self) -> None:
        """Test options returns saved schedule names."""
        entity = self._make_entity(
            saved_schedules={
                "weekday": make_mock_schedule(),
                "weekend": make_mock_schedule(),
            },
        )
        assert set(entity.options) == {"weekday", "weekend"}

    def test_options_empty_returns_placeholder(self) -> None:
        """Test options returns placeholder when empty."""
        entity = self._make_entity(saved_schedules={})
        assert entity.options == ["(none)"]

    def test_current_option(self) -> None:
        """Test current option reflects active saved name."""
        entity = self._make_entity(active_name="weekday")
        assert entity.current_option == "weekday"

    def test_current_option_none(self) -> None:
        """Test current option is None when no active saved schedule."""
        entity = self._make_entity(active_name=None)
        assert entity.current_option is None

    async def test_select_option(self) -> None:
        """Test selecting an option loads the schedule."""
        entity = self._make_entity(
            saved_schedules={"weekday": make_mock_schedule()},
        )
        await entity.async_select_option("weekday")
        entity.coordinator.async_load_saved_schedule.assert_called_once_with("weekday")
