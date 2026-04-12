"""Service handlers for the Ooler Sleep System integration."""

from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from ooler_ble_client import SleepScheduleNight, WarmWake

from .const import DOMAIN

if TYPE_CHECKING:
    from . import OolerConfigEntry

SERVICE_SAVE_SCHEDULE = "save_schedule"
SERVICE_DELETE_SCHEDULE = "delete_schedule"
SERVICE_LOAD_SCHEDULE = "load_schedule"
SERVICE_SET_SCHEDULE = "set_schedule"

_TIME_PARTS = 2
_MAX_DAY = 6


def _get_coordinator(hass: HomeAssistant, call: ServiceCall):
    """
    Resolve the coordinator from a service call target.

    Supports both device_id and entity_id targeting.
    """
    # Try device_id first
    device_ids = call.data.get("device_id")
    if device_ids:
        device_id = device_ids[0] if isinstance(device_ids, list) else device_ids
        device_registry = dr.async_get(hass)
        device_entry = device_registry.async_get(device_id)
        if device_entry is not None:
            for entry_id in device_entry.config_entries:
                entry: OolerConfigEntry | None = hass.config_entries.async_get_entry(
                    entry_id
                )
                if (
                    entry is not None
                    and entry.domain == DOMAIN
                    and entry.state is ConfigEntryState.LOADED
                ):
                    return entry.runtime_data

    # Fall back to entity_id
    entity_ids = call.data.get("entity_id")
    if entity_ids:
        entity_id = entity_ids[0] if isinstance(entity_ids, list) else entity_ids
        ent_registry = er.async_get(hass)
        ent_entry = ent_registry.async_get(entity_id)
        if ent_entry is not None and ent_entry.config_entry_id is not None:
            entry = hass.config_entries.async_get_entry(ent_entry.config_entry_id)
            if (
                entry is not None
                and entry.domain == DOMAIN
                and entry.state is ConfigEntryState.LOADED
            ):
                return entry.runtime_data

    msg = "No Ooler device found for the given target"
    raise HomeAssistantError(msg)


def _parse_time(value: str) -> time:
    """Parse a HH:MM string into a time object."""
    parts = value.split(":")
    if len(parts) != _TIME_PARTS:
        msg = f"Invalid time format '{value}', expected HH:MM"
        raise HomeAssistantError(msg)
    try:
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, TypeError) as err:
        msg = f"Invalid time '{value}'"
        raise HomeAssistantError(msg) from err


def _parse_nights(nights_data: list[dict[str, Any]]) -> list[SleepScheduleNight]:
    """Parse service call night data into SleepScheduleNight objects."""
    result: list[SleepScheduleNight] = []

    for night_def in nights_data:
        days = night_def.get("days")
        if not days or not isinstance(days, list):
            msg = "Each night entry must have a 'days' list"
            raise HomeAssistantError(msg)

        bedtime_str = night_def.get("bedtime")
        off_time_str = night_def.get("off_time")
        if not bedtime_str or not off_time_str:
            msg = "Each night entry must have 'bedtime' and 'off_time'"
            raise HomeAssistantError(msg)

        bedtime = _parse_time(bedtime_str)
        off_time = _parse_time(off_time_str)

        # Build temps list
        temps_data = night_def.get("temps")
        single_temp = night_def.get("temperature")

        if temps_data is not None:
            temps: list[tuple[time, int]] = []
            for entry in temps_data:
                t = _parse_time(entry["time"])
                temps.append((t, int(entry["temperature"])))
        elif single_temp is not None:
            temps = [(bedtime, int(single_temp))]
        else:
            msg = "Each night must have 'temperature' or 'temps'"
            raise HomeAssistantError(msg)

        # Parse warm wake
        warm_wake = None
        ww_data = night_def.get("warm_wake")
        if ww_data is not None:
            warm_wake = WarmWake(
                target_temp_f=int(ww_data["temperature"]),
                duration_min=int(ww_data["duration"]),
            )

        # Replicate across all specified days
        for day in days:
            if not 0 <= day <= _MAX_DAY:
                msg = f"Invalid day {day}, must be 0-6 (Monday-Sunday)"
                raise HomeAssistantError(msg)
            result.append(
                SleepScheduleNight(
                    day=int(day),
                    temps=temps,
                    off_time=off_time,
                    warm_wake=warm_wake,
                )
            )

    return result


def async_register_services(hass: HomeAssistant) -> None:
    """Register Ooler services."""

    async def handle_save_schedule(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call)
        name = call.data["name"]
        await coordinator.async_save_schedule(name)

    async def handle_delete_schedule(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call)
        name = call.data["name"]
        await coordinator.async_delete_saved_schedule(name)

    async def handle_load_schedule(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call)
        name = call.data["name"]
        await coordinator.async_load_saved_schedule(name)

    async def handle_set_schedule(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call)
        nights_data = call.data["nights"]
        nights = _parse_nights(nights_data)
        try:
            await coordinator.async_write_sleep_schedule(nights)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    hass.services.async_register(
        DOMAIN,
        SERVICE_SAVE_SCHEDULE,
        handle_save_schedule,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_SCHEDULE,
        handle_delete_schedule,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LOAD_SCHEDULE,
        handle_load_schedule,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_SCHEDULE,
        handle_set_schedule,
    )


def async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister Ooler services."""
    hass.services.async_remove(DOMAIN, SERVICE_SAVE_SCHEDULE)
    hass.services.async_remove(DOMAIN, SERVICE_DELETE_SCHEDULE)
    hass.services.async_remove(DOMAIN, SERVICE_LOAD_SCHEDULE)
    hass.services.async_remove(DOMAIN, SERVICE_SET_SCHEDULE)
