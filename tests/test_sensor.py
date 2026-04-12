"""Tests for the Ooler sensor entities."""

from __future__ import annotations

from datetime import time
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from ooler_ble_client import SleepScheduleNight, WarmWake

from custom_components.ooler.coordinator import OolerCoordinator
from custom_components.ooler.sensor import (
    OolerScheduleTonightSensor,
    OolerWaterLevelSensor,
    async_setup_entry,
)

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
    """Test platform setup creates sensor entities."""
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

    assert len(added_entities) == 2
    assert isinstance(added_entities[0], OolerWaterLevelSensor)
    assert isinstance(added_entities[1], OolerScheduleTonightSensor)


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


class TestOolerScheduleTonightSensor:
    """Tests for the schedule tonight sensor."""

    def _make_entity(
        self, *, tonight: SleepScheduleNight | None = None, connected: bool = True
    ) -> OolerScheduleTonightSensor:
        client = make_mock_client(connected=connected)
        coordinator = make_coordinator_with_client(client)
        coordinator.tonight_schedule = tonight
        return OolerScheduleTonightSensor(coordinator)

    def test_unique_id(self) -> None:
        """Test unique ID format."""
        entity = self._make_entity()
        assert entity.unique_id == f"{OOLER_ADDRESS}_schedule_tonight"

    def test_name(self) -> None:
        """Test entity name."""
        entity = self._make_entity()
        assert entity.name == "Schedule Tonight"

    def test_native_value_no_schedule(self) -> None:
        """Test value is None when no schedule tonight."""
        entity = self._make_entity(tonight=None)
        assert entity.native_value is None

    def test_native_value_with_schedule(self) -> None:
        """Test value is a human-readable schedule summary."""
        night = SleepScheduleNight(
            day=0,
            temps=[(time(22, 0), 68), (time(2, 0), 62)],
            off_time=time(6, 0),
            warm_wake=None,
        )
        entity = self._make_entity(tonight=night)
        assert entity.native_value == "10:00 PM-6:00 AM, 68\u00b0F"

    def test_native_value_empty_temps(self) -> None:
        """Test value is None when temps list is empty."""
        night = SleepScheduleNight(day=0, temps=[], off_time=time(6, 0), warm_wake=None)
        entity = self._make_entity(tonight=night)
        assert entity.native_value is None

    def test_extra_state_attributes_no_schedule(self) -> None:
        """Test attributes are None when no schedule tonight."""
        entity = self._make_entity(tonight=None)
        assert entity.extra_state_attributes is None

    def test_extra_state_attributes_with_schedule(self) -> None:
        """Test attributes contain full schedule details."""
        night = SleepScheduleNight(
            day=0,
            temps=[(time(22, 0), 68), (time(2, 0), 62)],
            off_time=time(6, 0),
            warm_wake=WarmWake(target_temp_f=116, duration_min=30),
        )
        entity = self._make_entity(tonight=night)
        attrs = entity.extra_state_attributes

        assert attrs is not None
        assert attrs["day"] == "monday"
        assert attrs["bedtime"] == "22:00"
        assert attrs["off_time"] == "06:00"
        assert len(attrs["temps"]) == 2
        assert attrs["temps"][0] == {"time": "22:00", "temp_f": 68}
        assert attrs["temps"][1] == {"time": "02:00", "temp_f": 62}
        assert attrs["warm_wake"] == {
            "target_temp_f": 116,
            "duration_min": 30,
        }

    def test_extra_state_attributes_no_warm_wake(self) -> None:
        """Test attributes without warm wake don't include warm_wake key."""
        night = SleepScheduleNight(
            day=4,
            temps=[(time(23, 0), 70)],
            off_time=time(8, 0),
            warm_wake=None,
        )
        entity = self._make_entity(tonight=night)
        attrs = entity.extra_state_attributes

        assert attrs is not None
        assert attrs["day"] == "friday"
        assert "warm_wake" not in attrs

    def test_available(self) -> None:
        """Test availability reflects connection state."""
        entity = self._make_entity(connected=True)
        assert entity.available is True

        entity = self._make_entity(connected=False)
        assert entity.available is False
