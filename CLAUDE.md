# Ooler Integration — Context for Claude Code

## Architecture

This is a Home Assistant custom component (`custom_components/ooler/`) that controls Ooler sleep system devices over Bluetooth Low Energy (BLE). It depends on the `ooler_ble_client` Python library (separate repo) for all BLE communication.

### Files

- `__init__.py` — Entry setup/unload. Creates `OolerCoordinator`, forwards platforms. ~20 lines.
- `coordinator.py` — `OolerCoordinator` class. Manages BLE connection lifecycle, reconnection, polling, temperature unit sync. This is where connection management lives.
- `entity.py` — `OolerEntity` base class. Provides `device_info`, `available`, and listener registration shared by all entity platforms.
- `climate.py` — Climate entity (thermostat control: power, temperature, fan mode). Registers the `clean_service`.
- `sensor.py` — Water level sensor entity.
- `switch.py` — Two switches: Cleaning (UV light) and Bluetooth Connection (enable/disable auto-connect).
- `config_flow.py` — Bluetooth discovery, GATT connection verification, reconfigure flow.
- `diagnostics.py` — Diagnostics platform for debugging.

### Library boundary

The integration never touches BLE/GATT directly. All BLE operations go through `ooler_ble_client`:

- `client.connect()` / `client.stop()` — connection lifecycle
- `client.set_power()`, `client.set_temperature()`, `client.set_mode()`, `client.set_clean()` — device commands
- `client.set_temperature_unit()` — toggle device display unit
- `client.async_poll()` — read all characteristics
- `client.register_callback()` — state change notifications
- `client.set_ble_device()` — update the BLEDevice for proxy routing
- `client.state` — `OolerBLEState` with current device state
- `client.is_connected` — connection status

The library handles GATT retries, `establish_connection()` via `bleak_retry_connector`, notification subscriptions, and `_connect_lock` serialization internally.

## Connection management

### Reconnection paths

Three mechanisms ensure reconnection when `connection_enabled` is `True`:

1. **BLE advertisement callback** (`_async_update_ble`) — fires when HA's scanner sees the device. Updates the BLEDevice and schedules a connect if disconnected.
2. **Library disconnect callback** (`_async_on_state_change`) — fires immediately when the connection drops. Schedules a staggered reconnect.
3. **Periodic timer** (`_async_reconnect_check`) — fires every 60 seconds. Refreshes BLEDevice from HA cache and attempts reconnect if disconnected.

### Connection deduplication

- `_schedule_connect()` checks `_connect_task.done()` to prevent duplicate tasks.
- `async_ensure_connected()` awaits any in-flight `_connect_task` before attempting its own connect.

### connection_enabled flag

- Set to `False` only by: the connection switch's `async_turn_off()` and `async_stop()` (teardown).
- Set to `True` only by: the connection switch's `async_turn_on()` and coordinator `__init__`.
- All reconnection paths check this flag before attempting to connect.
- Accidental disconnects leave the flag `True`, so auto-reconnect handles them.

### Stagger delay

Reconnect delay is deterministic per device (derived from MAC address hash, 0.5-2s). Only applies to auto-reconnects (`stagger=True`), not initial connects or manual switch toggles.

### Unload ordering

`async_stop()` sets `connection_enabled = False` before calling `client.stop()`. This prevents the disconnect callback from scheduling a reconnect on the old coordinator during integration reload.

`async_unload_entry()` calls `async_stop()` before `async_unload_platforms()` to give the BLE proxy time to tear down old GATT subscriptions before the new coordinator subscribes.

## Temperature unit sync

The Ooler's display temperature unit is synced to match HA's unit system on first connect only (`_unit_synced` flag). The GATT characteristic for set_temperature is always stored in Fahrenheit internally; the library converts based on the display unit setting.

## Testing

- 117 tests, 100% coverage required (`pyproject.toml` fail-under=100)
- Tests use `MagicMock`/`AsyncMock` for the library client
- `make_mock_hass()` closes coroutines passed to `async_create_task` to prevent unawaited coroutine warnings
- Run: `pytest tests/ --cov=custom_components/ooler --cov-report=term-missing`

## Known gotchas

- **ESP32 proxy slots**: Each Ooler uses 4 BLE notification slots. ESPHome provides 12; raw ESP-IDF provides 9. Multiple BLE devices on one proxy can exhaust slots.
- **Single BLE connection**: The Ooler only supports one active BLE connection. The Ooler app and HA cannot connect simultaneously.
- **Water level sensor**: Reports only 0%, 50%, or 100% — it's a very rough estimate.
- **Wattage sensor**: Removed (unreliable characteristic). Entities will show "unavailable" after upgrade.
- **Pause service**: Removed. Use the Bluetooth Connection switch instead.
