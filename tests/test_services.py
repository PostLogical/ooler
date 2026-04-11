"""Tests for the Ooler service handlers."""

from __future__ import annotations

from datetime import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from ooler_ble_client import SleepScheduleNight, WarmWake

from custom_components.ooler.const import DOMAIN
from custom_components.ooler.services import (
    _get_coordinator,
    _parse_nights,
    _parse_time,
    async_register_services,
    async_unregister_services,
)

from .conftest import OOLER_ADDRESS


def make_mock_call(
    data: dict, device_id: str = "device_123"
) -> ServiceCall:
    """Create a mock service call."""
    call = MagicMock(spec=ServiceCall)
    call.data = {**data, "device_id": device_id}
    return call


class TestParseTime:
    """Tests for _parse_time helper."""

    def test_valid_time(self) -> None:
        assert _parse_time("22:00") == time(22, 0)

    def test_valid_time_midnight(self) -> None:
        assert _parse_time("00:00") == time(0, 0)

    def test_valid_time_with_minutes(self) -> None:
        assert _parse_time("06:30") == time(6, 30)

    def test_invalid_format(self) -> None:
        with pytest.raises(HomeAssistantError, match="Invalid time format"):
            _parse_time("22")

    def test_invalid_values(self) -> None:
        with pytest.raises(HomeAssistantError, match="Invalid time"):
            _parse_time("25:00")


class TestParseNights:
    """Tests for _parse_nights helper."""

    def test_simple_single_temp(self) -> None:
        """Test parsing a simple single-temperature night."""
        nights = _parse_nights([
            {
                "days": [0, 1, 2],
                "bedtime": "22:00",
                "off_time": "06:00",
                "temperature": 68,
            }
        ])
        assert len(nights) == 3
        for i, night in enumerate(nights):
            assert night.day == i
            assert night.temps == [(time(22, 0), 68)]
            assert night.off_time == time(6, 0)
            assert night.warm_wake is None

    def test_multi_temp_zones(self) -> None:
        """Test parsing with multiple temperature zones."""
        nights = _parse_nights([
            {
                "days": [0],
                "bedtime": "22:00",
                "off_time": "06:00",
                "temps": [
                    {"time": "22:00", "temperature": 68},
                    {"time": "02:00", "temperature": 62},
                    {"time": "04:00", "temperature": 70},
                ],
            }
        ])
        assert len(nights) == 1
        assert len(nights[0].temps) == 3
        assert nights[0].temps[0] == (time(22, 0), 68)
        assert nights[0].temps[1] == (time(2, 0), 62)
        assert nights[0].temps[2] == (time(4, 0), 70)

    def test_with_warm_wake(self) -> None:
        """Test parsing with warm wake."""
        nights = _parse_nights([
            {
                "days": [0],
                "bedtime": "22:00",
                "off_time": "06:00",
                "temperature": 68,
                "warm_wake": {"temperature": 116, "duration": 30},
            }
        ])
        assert nights[0].warm_wake == WarmWake(target_temp_f=116, duration_min=30)

    def test_multiple_entries(self) -> None:
        """Test parsing weekday/weekend split."""
        nights = _parse_nights([
            {
                "days": [0, 1, 2, 3, 4],
                "bedtime": "22:00",
                "off_time": "06:00",
                "temperature": 68,
            },
            {
                "days": [5, 6],
                "bedtime": "23:00",
                "off_time": "08:00",
                "temperature": 70,
            },
        ])
        assert len(nights) == 7
        assert nights[4].day == 4
        assert nights[4].temps == [(time(22, 0), 68)]
        assert nights[5].day == 5
        assert nights[5].temps == [(time(23, 0), 70)]

    def test_missing_days(self) -> None:
        """Test error when days is missing."""
        with pytest.raises(HomeAssistantError, match="'days' list"):
            _parse_nights([{"bedtime": "22:00", "off_time": "06:00", "temperature": 68}])

    def test_missing_bedtime(self) -> None:
        """Test error when bedtime is missing."""
        with pytest.raises(HomeAssistantError, match="'bedtime' and 'off_time'"):
            _parse_nights([{"days": [0], "off_time": "06:00", "temperature": 68}])

    def test_missing_off_time(self) -> None:
        """Test error when off_time is missing."""
        with pytest.raises(HomeAssistantError, match="'bedtime' and 'off_time'"):
            _parse_nights([{"days": [0], "bedtime": "22:00", "temperature": 68}])

    def test_missing_temperature(self) -> None:
        """Test error when neither temperature nor temps provided."""
        with pytest.raises(HomeAssistantError, match="'temperature' or 'temps'"):
            _parse_nights([{"days": [0], "bedtime": "22:00", "off_time": "06:00"}])

    def test_invalid_day(self) -> None:
        """Test error for invalid day number."""
        with pytest.raises(HomeAssistantError, match="Invalid day 7"):
            _parse_nights([
                {"days": [7], "bedtime": "22:00", "off_time": "06:00", "temperature": 68}
            ])

    def test_empty_days_list(self) -> None:
        """Test error for empty days list."""
        with pytest.raises(HomeAssistantError, match="'days' list"):
            _parse_nights([
                {"days": [], "bedtime": "22:00", "off_time": "06:00", "temperature": 68}
            ])


class TestGetCoordinator:
    """Tests for _get_coordinator helper."""

    def test_no_device_id(self) -> None:
        """Test error when no device specified."""
        hass = MagicMock()
        call = MagicMock(spec=ServiceCall)
        call.data = {}
        with pytest.raises(HomeAssistantError, match="No device"):
            _get_coordinator(hass, call)

    def test_device_not_found(self) -> None:
        """Test error when device not in registry."""
        hass = MagicMock()
        call = make_mock_call({})
        with patch(
            "custom_components.ooler.services.dr.async_get"
        ) as mock_dr:
            mock_dr.return_value.async_get.return_value = None
            with pytest.raises(HomeAssistantError, match="not found"):
                _get_coordinator(hass, call)

    def test_no_ooler_entry(self) -> None:
        """Test error when device has no Ooler config entry."""
        hass = MagicMock()
        call = make_mock_call({})

        device_entry = MagicMock()
        device_entry.config_entries = {"some_other_entry"}

        other_entry = MagicMock()
        other_entry.domain = "other"
        other_entry.state = ConfigEntryState.LOADED

        with patch(
            "custom_components.ooler.services.dr.async_get"
        ) as mock_dr:
            mock_dr.return_value.async_get.return_value = device_entry
            hass.config_entries.async_get_entry.return_value = other_entry
            with pytest.raises(HomeAssistantError, match="No loaded Ooler"):
                _get_coordinator(hass, call)

    def test_found_coordinator(self) -> None:
        """Test successfully resolving coordinator."""
        hass = MagicMock()
        call = make_mock_call({})

        device_entry = MagicMock()
        device_entry.config_entries = {"entry_123"}

        mock_coordinator = MagicMock()
        config_entry = MagicMock()
        config_entry.domain = DOMAIN
        config_entry.state = ConfigEntryState.LOADED
        config_entry.runtime_data = mock_coordinator

        with patch(
            "custom_components.ooler.services.dr.async_get"
        ) as mock_dr:
            mock_dr.return_value.async_get.return_value = device_entry
            hass.config_entries.async_get_entry.return_value = config_entry
            result = _get_coordinator(hass, call)

        assert result is mock_coordinator

    def test_device_id_as_list(self) -> None:
        """Test device_id passed as a list."""
        hass = MagicMock()
        call = MagicMock(spec=ServiceCall)
        call.data = {"device_id": ["device_123"]}

        device_entry = MagicMock()
        device_entry.config_entries = {"entry_123"}

        mock_coordinator = MagicMock()
        config_entry = MagicMock()
        config_entry.domain = DOMAIN
        config_entry.state = ConfigEntryState.LOADED
        config_entry.runtime_data = mock_coordinator

        with patch(
            "custom_components.ooler.services.dr.async_get"
        ) as mock_dr:
            mock_dr.return_value.async_get.return_value = device_entry
            hass.config_entries.async_get_entry.return_value = config_entry
            result = _get_coordinator(hass, call)

        assert result is mock_coordinator


class TestServiceRegistration:
    """Tests for service registration/unregistration."""

    def test_register_services(self) -> None:
        """Test all services are registered."""
        hass = MagicMock()
        async_register_services(hass)

        registered = {
            call.args[1] for call in hass.services.async_register.call_args_list
        }
        assert registered == {
            "save_schedule",
            "delete_schedule",
            "load_schedule",
            "set_schedule",
        }

    def test_unregister_services(self) -> None:
        """Test all services are unregistered."""
        hass = MagicMock()
        async_unregister_services(hass)

        removed = {
            call.args[1] for call in hass.services.async_remove.call_args_list
        }
        assert removed == {
            "save_schedule",
            "delete_schedule",
            "load_schedule",
            "set_schedule",
        }


class TestServiceHandlers:
    """Tests for the service handler functions."""

    def _register_and_get_handler(self, hass: MagicMock, service_name: str):
        """Register services and return the handler for the named service."""
        async_register_services(hass)
        for call in hass.services.async_register.call_args_list:
            if call.args[1] == service_name:
                return call.args[2]
        raise ValueError(f"Service {service_name} not found")

    async def test_handle_save_schedule(self) -> None:
        """Test save_schedule handler calls coordinator."""
        hass = MagicMock()
        handler = self._register_and_get_handler(hass, "save_schedule")

        mock_coordinator = MagicMock()
        mock_coordinator.async_save_schedule = AsyncMock()

        call = make_mock_call({"name": "weekday"})

        with patch(
            "custom_components.ooler.services._get_coordinator",
            return_value=mock_coordinator,
        ):
            await handler(call)

        mock_coordinator.async_save_schedule.assert_called_once_with("weekday")

    async def test_handle_delete_schedule(self) -> None:
        """Test delete_schedule handler calls coordinator."""
        hass = MagicMock()
        handler = self._register_and_get_handler(hass, "delete_schedule")

        mock_coordinator = MagicMock()
        mock_coordinator.async_delete_saved_schedule = AsyncMock()

        call = make_mock_call({"name": "weekday"})

        with patch(
            "custom_components.ooler.services._get_coordinator",
            return_value=mock_coordinator,
        ):
            await handler(call)

        mock_coordinator.async_delete_saved_schedule.assert_called_once_with("weekday")

    async def test_handle_load_schedule(self) -> None:
        """Test load_schedule handler calls coordinator."""
        hass = MagicMock()
        handler = self._register_and_get_handler(hass, "load_schedule")

        mock_coordinator = MagicMock()
        mock_coordinator.async_load_saved_schedule = AsyncMock()

        call = make_mock_call({"name": "weekday"})

        with patch(
            "custom_components.ooler.services._get_coordinator",
            return_value=mock_coordinator,
        ):
            await handler(call)

        mock_coordinator.async_load_saved_schedule.assert_called_once_with("weekday")

    async def test_handle_set_schedule(self) -> None:
        """Test set_schedule handler parses and writes schedule."""
        hass = MagicMock()
        handler = self._register_and_get_handler(hass, "set_schedule")

        mock_coordinator = MagicMock()
        mock_coordinator.async_write_sleep_schedule = AsyncMock()

        call = make_mock_call({
            "nights": [
                {
                    "days": [0, 1],
                    "bedtime": "22:00",
                    "off_time": "06:00",
                    "temperature": 68,
                }
            ]
        })

        with patch(
            "custom_components.ooler.services._get_coordinator",
            return_value=mock_coordinator,
        ):
            await handler(call)

        mock_coordinator.async_write_sleep_schedule.assert_called_once()
        nights = mock_coordinator.async_write_sleep_schedule.call_args[0][0]
        assert len(nights) == 2
        assert nights[0].day == 0
        assert nights[1].day == 1

    async def test_handle_set_schedule_value_error(self) -> None:
        """Test set_schedule wraps ValueError as HomeAssistantError."""
        hass = MagicMock()
        handler = self._register_and_get_handler(hass, "set_schedule")

        mock_coordinator = MagicMock()
        mock_coordinator.async_write_sleep_schedule = AsyncMock(
            side_effect=ValueError("Too many events: 71 (max 70)")
        )

        call = make_mock_call({
            "nights": [
                {
                    "days": [0],
                    "bedtime": "22:00",
                    "off_time": "06:00",
                    "temperature": 68,
                }
            ]
        })

        with (
            patch(
                "custom_components.ooler.services._get_coordinator",
                return_value=mock_coordinator,
            ),
            pytest.raises(HomeAssistantError, match="Too many events"),
        ):
            await handler(call)
