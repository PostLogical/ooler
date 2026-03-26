"""Tests for the Ooler base entity."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.ooler.coordinator import OolerCoordinator
from custom_components.ooler.entity import OolerEntity

from .conftest import OOLER_ADDRESS, OOLER_NAME


def make_coordinator(connected: bool = True) -> OolerCoordinator:
    """Create a coordinator mock."""
    coordinator = MagicMock(spec=OolerCoordinator)
    coordinator.address = OOLER_ADDRESS
    coordinator.model = OOLER_NAME
    coordinator.is_connected = connected
    coordinator.async_add_listener = MagicMock(return_value=lambda: None)
    return coordinator


class TestOolerEntity:
    """Tests for the OolerEntity base class."""

    def test_has_entity_name(self) -> None:
        """Test has_entity_name is set."""
        coordinator = make_coordinator()
        entity = OolerEntity(coordinator)
        assert entity.has_entity_name is True

    def test_device_info(self) -> None:
        """Test device_info contains correct data."""
        coordinator = make_coordinator()
        entity = OolerEntity(coordinator)
        info = entity.device_info
        assert info is not None
        assert ("bluetooth", OOLER_ADDRESS) in info["connections"]

    def test_available_connected(self) -> None:
        """Test available when connected."""
        entity = OolerEntity(make_coordinator(connected=True))
        assert entity.available is True

    def test_available_disconnected(self) -> None:
        """Test unavailable when disconnected."""
        entity = OolerEntity(make_coordinator(connected=False))
        assert entity.available is False

    async def test_async_added_to_hass(self, hass) -> None:
        """Test callback registration on add to hass."""
        coordinator = make_coordinator()
        entity = OolerEntity(coordinator)
        entity.hass = hass
        entity.entity_id = "test.ooler_entity"

        removers: list = []
        entity.async_on_remove = lambda cb: removers.append(cb)

        await entity.async_added_to_hass()

        coordinator.async_add_listener.assert_called_once()
        assert len(removers) == 1

    def test_handle_state_update(self) -> None:
        """Test _handle_state_update triggers HA state write."""
        coordinator = make_coordinator()
        entity = OolerEntity(coordinator)
        entity.async_write_ha_state = MagicMock()

        entity._handle_state_update()
        entity.async_write_ha_state.assert_called_once()
