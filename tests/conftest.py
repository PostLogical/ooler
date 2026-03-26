"""Fixtures for Ooler integration tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.ooler.const import CONF_MODEL, DOMAIN

OOLER_ADDRESS = "84:71:27:55:0D:71"
OOLER_NAME = "OOLER-92106080601"


def make_service_info(
    address: str = OOLER_ADDRESS,
    name: str = OOLER_NAME,
) -> BluetoothServiceInfoBleak:
    """Create a BluetoothServiceInfoBleak for testing."""
    return BluetoothServiceInfoBleak(
        name=name,
        address=address,
        rssi=-60,
        manufacturer_data={},
        service_data={},
        service_uuids=[],
        source="local",
        device=MagicMock(),
        advertisement=MagicMock(),
        connectable=True,
        time=0.0,
        tx_power=None,
    )


def make_mock_state() -> MagicMock:
    """Create a mock OolerBLEState."""
    state = MagicMock()
    state.power = True
    state.mode = "Regular"
    state.set_temperature = 72
    state.actual_temperature = 74
    state.temperature_unit = "F"
    state.water_level = 80
    state.clean = False
    state.connected = True
    return state


def make_mock_client(connected: bool = True) -> MagicMock:
    """Create a mock OolerBLEDevice."""
    client = MagicMock()
    client.is_connected = connected
    client.state = make_mock_state()
    client.connect = AsyncMock()
    client.stop = AsyncMock()
    client.async_poll = AsyncMock()
    client.set_power = AsyncMock()
    client.set_mode = AsyncMock()
    client.set_temperature = AsyncMock()
    client.set_clean = AsyncMock()
    client.set_temperature_unit = AsyncMock()
    client.set_ble_device = MagicMock()
    client.register_callback = MagicMock(return_value=lambda: None)
    return client


@pytest.fixture
def mock_client() -> MagicMock:
    """Return a mock OolerBLEDevice."""
    return make_mock_client()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    """Enable custom integrations for all tests."""
    yield


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Override async_setup_entry to prevent actual setup."""
    with patch(
        "custom_components.ooler.async_setup_entry",
        return_value=True,
    ) as mock:
        yield mock


@pytest.fixture
def mock_config_entry(hass: HomeAssistant) -> ConfigEntry:
    """Create a mock config entry."""
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title=OOLER_NAME,
        data={CONF_MODEL: OOLER_NAME},
        source="bluetooth",
        unique_id=OOLER_ADDRESS,
        discovery_keys={},
    )
    entry.add_to_hass(hass)
    return entry
