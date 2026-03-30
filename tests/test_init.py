"""Tests for the Ooler integration setup."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from custom_components.ooler import (
    PLATFORMS,
    OolerConfigEntry,
    async_setup_entry,
    async_unload_entry,
)

from .conftest import OOLER_ADDRESS, OOLER_NAME


def test_platforms() -> None:
    """Test platform list is correct."""
    assert Platform.CLIMATE in PLATFORMS
    assert Platform.SENSOR in PLATFORMS
    assert Platform.SWITCH in PLATFORMS


async def test_setup_entry() -> None:
    """Test async_setup_entry creates coordinator and forwards platforms."""
    hass = MagicMock(spec=HomeAssistant)
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()

    mock_coordinator = MagicMock()
    mock_coordinator.async_start = AsyncMock(return_value=[lambda: None])

    entry = MagicMock(spec=OolerConfigEntry)
    entry.unique_id = OOLER_ADDRESS
    entry.data = {"model": OOLER_NAME}
    entry.async_on_unload = MagicMock()

    with patch(
        "custom_components.ooler.OolerCoordinator",
        return_value=mock_coordinator,
    ):
        result = await async_setup_entry(hass, entry)

    assert result is True
    assert entry.runtime_data == mock_coordinator
    hass.config_entries.async_forward_entry_setups.assert_called_once()
    entry.async_on_unload.assert_called()


async def test_unload_entry() -> None:
    """Test async_unload_entry stops coordinator."""
    hass = MagicMock(spec=HomeAssistant)
    hass.config_entries = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

    mock_coordinator = MagicMock()
    mock_coordinator.async_stop = AsyncMock()

    entry = MagicMock(spec=OolerConfigEntry)
    entry.runtime_data = mock_coordinator

    result = await async_unload_entry(hass, entry)

    assert result is True
    mock_coordinator.async_stop.assert_called_once()


async def test_unload_entry_failure() -> None:
    """Test async_unload_entry still stops coordinator on platform unload failure."""
    hass = MagicMock(spec=HomeAssistant)
    hass.config_entries = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)

    mock_coordinator = MagicMock()
    mock_coordinator.async_stop = AsyncMock()

    entry = MagicMock(spec=OolerConfigEntry)
    entry.runtime_data = mock_coordinator

    result = await async_unload_entry(hass, entry)

    assert result is False
    mock_coordinator.async_stop.assert_called_once()
