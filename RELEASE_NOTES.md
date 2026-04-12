# Release Notes

## 2026.3.7b6

Full-featured release of the Ooler Sleep System integration for Home Assistant. Requires `ooler_ble_client` 0.10.0.

This release adds complete sleep schedule management, comprehensive schedule services, a saved-schedule library, and connection reliability improvements built on top of the extracted coordinator architecture. 236 tests enforce 100% code coverage.

---

### Sleep schedule management

- **Sleep Schedule switch** — toggle the device's active sleep schedule on or off. When disabled the integration caches the schedule so it can be re-enabled without re-entering it. The switch is unavailable until a schedule exists on the device.
- **Saved Schedule select** — name and store schedules for later use. Selecting a saved schedule writes it to the device. Schedules persist across restarts in per-device HA storage.
- **Schedule Tonight sensor** — shows tonight's program at a glance (e.g. "10:00 PM–6:00 AM, 68 °F"). Detailed attributes include bedtime, off time, temperature zones, and warm-wake configuration.
- **Climate entity attributes** — `sleep_schedule_days` and `sleep_schedule_nights` expose the full schedule when one is active, including per-night temperature zones and warm-wake settings.
- **Clock sync** — the device clock is synced to HA's timezone on every connection and every four hours. Required when HA is the sole BLE client because the Ooler app normally handles clock management.

> **Note:** The Ooler app maintains its own schedule database and never reads from the device. If HA disables or changes the schedule the app will not reflect it. Toggling a schedule in the app will overwrite whatever HA wrote.

### Schedule services

Six services are registered under the `ooler` domain:

| Service | Description |
|---|---|
| `get_schedule` | Return the current device schedule in the same YAML format accepted by `set_schedule`. Response-only service — call it to inspect or copy the active schedule. |
| `set_schedule` | Write a schedule directly to the device. Supports single temperature per night, multiple mid-night temperature changes, warm-wake configuration, and day grouping. |
| `save_schedule` | Save the current device schedule under a name for later use. |
| `load_schedule` | Write a previously saved schedule to the device. |
| `delete_schedule` | Remove a saved schedule by name. |
| `clean_service` | Activate the UV cleaning light (entity service on the climate entity). |

`set_schedule` accepts a list of night definitions. Each entry specifies the days it applies to, bedtime and off time, either a single temperature or a list of timed temperature changes, and an optional warm-wake block:

```yaml
service: ooler.set_schedule
target:
  device_id: <your device>
data:
  nights:
    - days: [0, 1, 2, 3, 4]   # Monday–Friday
      bedtime: "22:00"
      off_time: "06:00"
      temperature: 68
      warm_wake:
        temperature: 116
        duration: 30
    - days: [5, 6]             # Saturday–Sunday
      bedtime: "23:00"
      off_time: "08:00"
      temps:
        - time: "23:00"
          temperature: 70
        - time: "02:00"
          temperature: 65
```

Call `get_schedule` first to see the device's current schedule in this exact format.

### Connection reliability

- Fixed duplicate BLE notification subscriptions during integration reload by disconnecting before platform unload.
- Suppressed reconnect attempts during teardown to prevent stale coordinator reconnection on reload.
- Stagger delay (0.5–2 s, derived from MAC address) applies only to auto-reconnects, not initial or manual connections.
- Added 60-second periodic reconnection fallback for silently dropped BLE connections.
- BLEDevice is seeded from HA's Bluetooth cache on setup to prevent initial connect failures.
- The Bluetooth Connection switch properly suppresses all three auto-reconnect paths (BLE advertisement, disconnect callback, periodic timer) when turned off.
- Schedule is read from the device on every successful connect, regardless of the connect path.

### Integration architecture

- Extracted `OolerCoordinator` from the climate entity. The coordinator owns the BLE connection lifecycle, reconnection, polling, temperature-unit sync, clock sync, and schedule storage.
- Extracted `OolerEntity` base class providing shared `device_info`, `available`, and listener registration for all entity platforms.
- Added reconfiguration flow for re-verifying BLE connections without removing the device.
- Added diagnostics platform exposing connection state, device state, and schedule metadata.
- Added strict typing with `py.typed` marker.
- Entity categories, translation keys, and proper HA exception types applied throughout.
- Replaced advertisement-based pairing with GATT connection verification during config flow.

### Removed features

- **Wattage sensor** — removed due to unreliable BLE characteristic. Existing entities will show "unavailable" after upgrade.
- **Pause service** — removed. Use the Bluetooth Connection switch to disconnect instead.

### Testing and CI

- 236 tests with 100% code coverage, enforced via `pytest --cov` fail-under.
- GitHub Actions CI workflow running on Python 3.13 with ruff linting.
- Tests use `MagicMock`/`AsyncMock` for the BLE client; no real hardware required.

### Library changelog (0.7.1 → 0.10.0)

The underlying `ooler_ble_client` library was upgraded through several releases:

- **0.10.0** — Sleep schedule read/write, clock sync, temperature validation, consistent `TemperatureUnit` type.
- **0.9.0** — Stable release consolidating beta fixes.
- **0.8.x** — Consistent exception types, writes-when-off support, GATT retry improvements.

### Compatibility notes

- **ESP32 proxy slots:** Each Ooler uses 4 BLE notification slots. ESPHome provides 12 per proxy; raw ESP-IDF provides 9. Multiple BLE devices on one proxy can exhaust slots.
- **Single BLE connection:** The Ooler only supports one active BLE connection. The Ooler app and HA cannot be connected simultaneously.
- **Water level sensor:** Reports only 0 %, 50 %, or 100 % — it is a rough estimate from the device hardware.
