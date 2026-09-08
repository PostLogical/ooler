# Ooler Integration — Context for Claude Code

## Architecture

This is a Home Assistant custom component (`custom_components/ooler/`) that controls Ooler sleep system devices over Bluetooth Low Energy (BLE). It depends on the `ooler_ble_client` Python library (separate repo) for all BLE communication.

### Files

- `__init__.py` — Entry setup/unload. Creates `OolerCoordinator`, forwards platforms, registers/unregisters services. ~20 lines.
- `coordinator.py` — `OolerCoordinator` class. Manages BLE connection lifecycle, reconnection, polling, temperature unit sync, sleep schedule state, clock sync, and saved schedule persistence.
- `entity.py` — `OolerEntity` base class. Provides `device_info`, `available`, and listener registration shared by all entity platforms.
- `climate.py` — Climate entity (thermostat control: power, temperature, fan mode).
- `sensor.py` — Two sensors: Water level (%) and Schedule Tonight (tonight's sleep schedule summary with detailed attributes).
- `select.py` — Saved Schedule select entity. Lets users pick from named saved schedules to load onto the device.
- `switch.py` — Three switches: Deep Clean (start/cancel a deep clean), Sleep Schedule (toggle active schedule on/off with caching), and Bluetooth Connection (enable/disable auto-connect).
- `services.py` — Service handlers: `get_schedule`, `set_schedule`, `save_schedule`, `load_schedule`, `delete_schedule`, `clean_service`. Supports both device_id and entity_id targeting.
- `services.yaml` — Service definitions for the UI.
- `config_flow.py` — Bluetooth discovery, GATT connection verification, reconfigure flow.
- `diagnostics.py` — Diagnostics platform including connection health metrics (subscription mismatches, forced reconnects).
- `const.py` — Constants and logger.

### Library boundary

The integration never touches BLE/GATT directly. All BLE operations go through `ooler_ble_client`:

- `client.connect()` / `client.stop()` — connection lifecycle
- `client.set_power()`, `client.set_temperature()`, `client.set_mode()`, `client.set_deep_clean()` — device commands
- `client.set_temperature_unit()` — toggle device display unit
- `client.async_poll()` — read all characteristics (also runs poll/state consistency detection)
- `client.register_callback()` — state change notifications
- `client.register_connection_event_callback()` — connection event notifications (mismatch, recovery, forced reconnect, setpoint override, clean-asserted-while-off)
- `client.set_ble_device()` — update the BLEDevice for proxy routing
- `client.read_sleep_schedule()` — read schedule from device (called once on connect)
- `client.set_sleep_schedule()` / `client.clear_sleep_schedule()` — write/clear schedule
- `client.sync_clock()` — sync device clock to HA timezone
- `client.state` — `OolerBLEState` with current device state
- `client.sleep_schedule` — `OolerSleepSchedule` with current schedule (read on connect only)
- `client.is_connected` — connection status

The library handles GATT retries, `establish_connection()` via `bleak_retry_connector`, notification subscriptions, poll/state consistency detection, and `_connect_lock` serialization internally.

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

### BLE proxy resilience

ESPHome Bluetooth proxies can drop BLE notification subscriptions without disconnecting. The library's poll/state consistency detector (in `async_poll()`) compares fresh GATT reads against cached state on four notify-backed fields. On mismatch:

1. **Tier 1**: Re-subscribe notifications on existing connection (`SUBSCRIPTION_MISMATCH` → `SUBSCRIPTION_RECOVERED`)
2. **Tier 2**: Full forced reconnect if next poll still shows mismatch (`FORCED_RECONNECT`)

The coordinator handles these via `_async_on_connection_event()` and tracks them in diagnostics (`_last_subscription_mismatch`, `_forced_reconnect_counts`).

## Temperature unit sync

The Ooler's display temperature unit is synced to match HA's unit system on first connect only (`_unit_synced` flag). The GATT characteristic for set_temperature is always stored in Fahrenheit internally; the library converts based on the display unit setting.

## Sleep schedules

### Device model

The device stores one active schedule as a flat list of `(minute_of_week, temp_f)` events. The library parses these into `OolerSleepSchedule` with `list[SleepScheduleNight]`, each night having optional `WarmWake`.

### Integration behavior

- Schedule is read once on connect (`_async_post_connect`) — not polled, since only one BLE client connects at a time.
- Sleep Schedule switch: toggle caches the schedule on disable (`clear_sleep_schedule`), restores on enable (`set_sleep_schedule`).
- Saved schedules are stored per-device in `homeassistant.helpers.storage.Store` and persist across restarts.
- Clock is synced to HA timezone on connect and every 4 hours (`CLOCK_SYNC_INTERVAL`).

### App compatibility

The Ooler app does not read schedule state from the device; it assumes it is the sole arbiter. Schedules with per-night variation (different temps on different days) work with the device but the app may not display them correctly.

## Deep clean vs. UV clean

The device's `CLEAN` characteristic carries **two** states, and library >=1.1.0b12 splits them:

- `state.deep_clean` — the ~45 minute cycle a person starts (`set_deep_clean(True)`, or the vendor app). It forces `SET_TEMP` to 75F, ends by powering the unit off, and is the one that arms the setpoint-override bug. The library derives it from characteristic state, not from provenance, so an app-started clean is recognised on the first poll after reconnect.
- `state.uv_clean` — a cycle the device runs by itself: ~3-5 minutes once per hour of runtime, only while powered, with no client involvement and no way to start or stop it. **There is no setter and there will not be one.** The *name* is an inference: the Ooler manual describes an automatic "integrated water treatment system, which includes a UV light", which fits. What the unit physically does during the window is **not established** — do not write user-facing copy that claims it (e.g. that cooling pauses). The timing, the power gate and the absence of a forced setpoint are measured; the identification is not.

Both read false when `CLEAN` is asserted on a **powered-off** unit (observed once, latched ~9 hours, cause unknown). That case emits `CLEAN_ASSERTED_WHILE_OFF` on every poll while it holds, which the coordinator **counts** (never accumulates) under the `clean_asserted_while_off` diagnostics key — the only durable trace, since neither state field records it.

Integration notes:

- The Deep Clean switch binds to `deep_clean` / `set_deep_clean`. Before this split it tracked the raw bit and flicked on for one poll every hour.
- Its `unique_id` is still `{address}_cleaning_binary_sensor`. Do not change it — that would orphan every existing entity.
- `uv_clean` is deliberately **not** exposed as an entity. It is not actionable, not controllable, and an hourly-toggling entity is noise; it lives in the state object and diagnostics only. The README explains the cycle to users instead.
- `set_deep_clean(False)` on a powered-off unit raises `DeviceOffError` → `ServiceValidationError` (`set_deep_clean_while_off`), same pattern as `set_temperature` / `set_mode`.
- The `ooler.clean_service` service id is unchanged even though it now says "deep clean" — renaming it would silently break users' automations at runtime.
- A UV cycle misread as a deep clean (only possible when the user's setpoint is already 75) cannot trigger the setpoint-override auto-fix: completion is keyed on a power-off while `deep_clean` is true, and a misread clears while the unit is still powered.

Full evidence for the split: `notes/ooler_clean_flag_20260905/`. Integration-side design decisions: `notes/clean_split_integration_reply.md`.

## Setpoint-override firmware bug

Some Ooler units have a firmware fault: after a **deep clean cycle runs to completion**, the device discards the user's setpoint and reverts to an older stored value shortly after it next powers off. The library detects and corrects this, surfacing it through connection events.

### Library behavior — and an important caveat

- After a completed deep clean the library applies a **0-second clean auto-fix** (power on → clean → re-write setpoint → power off) and emits `SETPOINT_OVERRIDE_FIXED`; if the correction can't be applied it emits `SETPOINT_OVERRIDE_UNFIXABLE`.
- **The auto-fix is unconditional.** It runs after *every* completed deep clean, not only when a genuine setpoint divergence is observed. So `SETPOINT_OVERRIDE_FIXED` fires — and the coordinator logs "corrected it automatically" and increments `fix_attempts` — even when the device did not actually need fixing. On firmware that fixes this bug, or on units that never exhibited it, the auto-fix still runs and still logs a correction that was really a no-op. Mostly harmless (a brief pump run and a transient setpoint blip in the device's history, both called out in the log message), but the "fixed" log line and the `fix_attempts` diagnostic count **completed deep cleans, not confirmed corrections.**

### Integration behavior

- `_async_on_connection_event` (coordinator) handles both events: logs an info line on `SETPOINT_OVERRIDE_FIXED`, tracks counts/last-seen under the `setpoint_override` diagnostics key, and on `SETPOINT_OVERRIDE_UNFIXABLE` raises a device-named repair issue.
- The repair issue is deleted before it is (re)created (`async_delete_issue` → `async_create_issue`) so an *Ignored* card re-notifies on the next recurrence; its link rides on `learn_more_url`, not in the translated description (hassfest forbids URLs in translation strings).
- The integration makes no device-state judgment of its own here — it only reacts to the library's events.

## Testing

- 259 tests, 100% coverage required (`pyproject.toml` fail-under=100)
- Tests use `MagicMock`/`AsyncMock` for the library client
- `make_mock_hass()` closes coroutines passed to `async_create_task` to prevent unawaited coroutine warnings
- Run: `pytest tests/ --cov=custom_components/ooler --cov-report=term-missing`

## Known gotchas

- **ESP32 proxy slots**: Each Ooler uses 4 BLE notification slots. ESPHome provides 12; raw ESP-IDF provides 9. Multiple BLE devices on one proxy can exhaust slots.
- **Single BLE connection**: The Ooler only supports one active BLE connection. The Ooler app and HA cannot connect simultaneously.
- **Water level sensor**: Reports only 1%, 50%, or 100% — a very rough estimate. The library (>=1.1.0b10) filters a placeholder `0` the firmware reports on ~1% of connects before it has a real value; `WATER_LEVEL_RANGE`/`ACTUAL_TEMP_RANGE_*` in the library's const gate these.
- **Temperature range**: Valid temps are 54-116F, plus special values 45 (LO) and 120 (HI).
