"""Tests for the Ooler sensor entities."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant

from custom_components.ooler.coordinator import OolerCoordinator
from custom_components.ooler.sensor import OolerWaterLevelSensor, async_setup_entry

from .conftest import OOLER_ADDRESS, OOLER_NAME, make_mock_client


def make_coordinator_with_client(client: MagicMock) -> OolerCoordinator:
    """Create a coordinator with a mocked client."""
    coordinator = MagicMock(spec=OolerCoordinator)
    coordinator.address = OOLER_ADDRESS
    coordinator.model = OOLER_NAME
    coordinator.client = client
    coordinator.is_connected = client.is_connected
    return coordinator


async def test_async_setup_entry() -> None:
    """Test platform setup creates sensor entity."""
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
    assert isinstance(added_entities[0], OolerWaterLevelSensor)


class TestOolerWaterLevelSensor:
    """Tests for the water level sensor."""

    def _make_entity(self, *, connected: bool = True) -> OolerWaterLevelSensor:
        client = make_mock_client(connected=connected)
        coordinator = make_coordinator_with_client(client)
        return OolerWaterLevelSensor(coordinator)

    def test_unique_id(self) -> None:
        """Test unique ID format."""
        entity = self._make_entity()
        assert entity.unique_id == f"{OOLER_ADDRESS}_water_level_sensor"

    def test_name(self) -> None:
        """Test entity name."""
        entity = self._make_entity()
        assert entity.name == "Water Level"

    def test_native_value(self) -> None:
        """Test water level value."""
        entity = self._make_entity()
        assert entity.native_value == 80

    def test_native_value_none(self) -> None:
        """Test water level when state returns None."""
        entity = self._make_entity()
        entity.coordinator.client.state.water_level = None
        assert entity.native_value is None

    def test_available(self) -> None:
        """Test availability reflects connection state."""
        entity = self._make_entity(connected=True)
        assert entity.available is True

        entity = self._make_entity(connected=False)
        assert entity.available is False

    def test_unit(self) -> None:
        """Test unit of measurement is percentage."""
        entity = self._make_entity()
        assert entity.native_unit_of_measurement == "%"
