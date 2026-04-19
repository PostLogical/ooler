# Ooler

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

[![Ruff][ruff-shield]][ruff]

[![hacs][hacsbadge]][hacs]
[![Project Maintenance][maintenance-shield]][user_profile]
[![BuyMeCoffee][buymecoffeebadge]][buymecoffee]

[![Discord][discord-shield]][discord]
[![Community Forum][forum-shield]][forum]

This custom Home Assistant component controls your Ooler Sleep System over a Bluetooth connection. It is fully compatible with ESPHome Bluetooth Proxies, so if your server is not in range of your Ooler, you can set up an ESP32 in your bedroom to relay the connection.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.][my-badge]][my-link]

**This component will set up the following platforms.**

| Platform  | Description                                                                     |
| --------- | ------------------------------------------------------------------------------- |
| `climate` | Control power, fan speed, and temperature. Shows current temp and HVAC action.  |
| `sensor`  | Water level (100%, 50%, or 1%) and tonight's sleep schedule summary.            |
| `select`  | Choose from saved sleep schedules to load onto the device.                      |
| `switch`  | Toggle cleaning mode, sleep schedule, or Bluetooth connection.                  |

### Temperature units

The integration automatically syncs the Ooler's temperature unit to match your Home Assistant unit system (metric = C, imperial = F). This ensures temperatures are displayed correctly in both HA and on the Ooler's physical display. If you need a different unit on the device, please [open an issue](https://github.com/PostLogical/ooler/issues).

### Supported devices

- **Ooler Sleep System** (all models with BLE GATT interface)

The Dock Pro (Ooler's successor) uses a cloud API and is not supported by this integration. See [sleepme_thermostat](https://github.com/rsampayo/sleepme_thermostat) for Dock Pro support.

### Supported functions

| Function | Entity | Description |
| --- | --- | --- |
| Power on/off | `climate` | Turn the Ooler on or off |
| Temperature control | `climate` | Set target water temperature |
| Fan mode | `climate` | Silent, Regular, or Boost |
| Current temperature | `climate` | Live water temperature reading |
| HVAC action | `climate` | Shows Heating, Cooling, or Idle |
| Water level | `sensor` | Rough reservoir level (0%, 50%, or 100%) |
| Schedule tonight | `sensor` | Summary of tonight's schedule (bedtime, off-time, starting temp) with full details in attributes |
| Saved schedule | `select` | Pick a saved schedule to load onto the device |
| Sleep schedule | `switch` | Enable/disable the active sleep schedule on the device |
| Cleaning mode | `switch` | Start/stop UV cleaning cycle |
| Bluetooth connection | `switch` | Manually disconnect to free the connection for the Ooler app |

### Sleep schedules

The integration reads and writes sleep schedules directly on the Ooler device. Schedules define per-night temperature programs with bedtime, off-time, and optional mid-night temperature changes and warm wake ramps. If you are only using Home Assistant with your Ooler, then it may be easier to implement your schedule as an automation in HA rather than use the built-in sleep schedule functionality, but if you want to keep using the functionality like in the Ooler app or care about it being built in to the device, then here you go.

**The easiest way to get started** is to create a schedule in the Ooler app first, then use `ooler.save_schedule` in HA to save it with a name (e.g., "weekday"). The app only supports applying the same schedule to every day it covers, but once the schedule is on the device, HA can read and save it for later use. You can also use `ooler.get_schedule` to read the device schedule, edit it manually (e.g., to add per-night variation or warm wake ramps), and write it back with `ooler.set_schedule`.

**App compatibility note:** The Ooler app does not read schedule state; it assumes that it is the sole arbiter of truth and will thus be out of sync with the device's loaded schedule until it overwrites with one of its own. (e.g. If you create a schedule in the app and enable it, then turn it off in HA, the Ooler app will think it is still enabled. Or if you create a new schedule in HA and then open the app and click the refresh button, your schedule will never appear since the app doesn't read from schedules from the device).

You can manage schedules through services:

| Service | Description |
| --- | --- |
| `ooler.set_schedule` | Write a schedule directly to the device (days, bedtime, off-time, temps, warm wake) |
| `ooler.get_schedule` | Read the current device schedule (returns the same format `set_schedule` accepts) |
| `ooler.save_schedule` | Save the current device schedule with a name for later use |
| `ooler.load_schedule` | Load a previously saved schedule onto the device |
| `ooler.delete_schedule` | Delete a saved schedule |

Saved schedules persist across HA restarts. The device only holds one active schedule at a time; saved schedules are stored by the integration and loaded onto the device when selected.

The **Schedule Tonight** sensor shows a glance view of tonight's program, with full details (temps list, warm wake settings) available as entity attributes. The **Sleep Schedule** switch toggles the active schedule on/off — disabling it caches the schedule so it can be re-enabled without recreating it.

The device clock is synced to your Home Assistant timezone on connect and every 4 hours to keep schedule timing accurate.

#### Schedule examples

**Simple weeknight schedule** — cool to 68F from 10pm to 7am, Monday through Friday:
```yaml
service: ooler.set_schedule
target:
  entity_id: climate.ooler_XXXX
data:
  nights:
    - days: [0, 1, 2, 3, 4]
      bedtime: "22:00"
      off_time: "07:00"
      temperature: 68
```

**Weekend schedule with warm wake** — cool to 65F, then warm to 72F over 30 minutes before off-time:
```yaml
service: ooler.set_schedule
target:
  entity_id: climate.ooler_XXXX
data:
  nights:
    - days: [5, 6]
      bedtime: "23:00"
      off_time: "09:00"
      temperature: 65
      warm_wake:
        temperature: 72
        duration: 30
```

**Mid-night temperature changes** — start cool, warm up overnight:
```yaml
service: ooler.set_schedule
target:
  entity_id: climate.ooler_XXXX
data:
  nights:
    - days: [0, 1, 2, 3, 4]
      bedtime: "22:00"
      off_time: "07:00"
      temps:
        - time: "22:00"
          temperature: 66
        - time: "02:00"
          temperature: 72
```

**Combined weekday + weekend** — different schedules in one call:
```yaml
service: ooler.set_schedule
target:
  entity_id: climate.ooler_XXXX
data:
  nights:
    - days: [0, 1, 2, 3, 4]
      bedtime: "22:00"
      off_time: "06:30"
      temperature: 68
      warm_wake:
        temperature: 74
        duration: 20
    - days: [5, 6]
      bedtime: "23:30"
      off_time: "09:00"
      temperature: 65
```

**Read, edit, and re-apply** — use `get_schedule` in Developer Tools > Services (with "Return response" enabled) to see the current schedule in the exact format `set_schedule` accepts, then copy and modify it:
```yaml
service: ooler.get_schedule
target:
  entity_id: climate.ooler_XXXX
```

**Save and manage named schedules:**
```yaml
# Save the current device schedule
service: ooler.save_schedule
target:
  entity_id: climate.ooler_XXXX
data:
  name: "weekday"

# Load it back later
service: ooler.load_schedule
target:
  entity_id: climate.ooler_XXXX
data:
  name: "weekday"

# Delete when no longer needed
service: ooler.delete_schedule
target:
  entity_id: climate.ooler_XXXX
data:
  name: "weekday"
```

Schedule services target any Ooler entity (e.g., the climate entity). Device and area targeting also work through the HA UI. Days are numbered 0=Monday through 6=Sunday. Temperatures are in Fahrenheit (the device's internal format). Valid temperatures are 54-116F, plus the special values 45 (LO) and 120 (HI).

### Data updates

The integration maintains a persistent BLE GATT connection to each Ooler device. State updates (power, temperature, mode) are pushed in real-time via GATT notifications. Water level and cleaning status are polled every 5 minutes. The sleep schedule is read once on connect (since only one BLE client can be connected at a time, it can't change while HA is connected).

If the connection drops, the integration reconnects automatically -- both immediately on disconnect and via a 60-second periodic fallback. When multiple devices reconnect simultaneously (e.g., after a proxy restart), attempts are staggered to avoid overwhelming the proxy's connection slots.

#### BLE proxy resilience

ESPHome Bluetooth proxies can occasionally drop BLE notification subscriptions without disconnecting. The integration detects these missed notifications by comparing polled state against the last notified state. When a mismatch is found, it automatically re-subscribes or forces a full reconnect if needed. These events are logged and tracked in device diagnostics for troubleshooting.

![oolerlogo][oolerlogo]

## Installation

### HACS

1. Open HACS in your Home Assistant instance.
2. Click the three-dot menu in the top right and select "Custom repositories".
3. Add `https://github.com/PostLogical/ooler` with category "Integration".
4. Find the integration as `Ooler` and click install.
5. Restart Home Assistant.

### Manual

1. Copy the `custom_components/ooler/` folder to your HA `custom_components/` directory.
2. Restart Home Assistant.

## Setup

1. In the HA UI go to "Settings" -> "Devices & Services" -> "Integrations".
2. Your Ooler should appear in the discovered integrations automatically. You can also click the + sign and search for "Ooler".
3. If your Ooler is not discovered, make sure it is powered on and not connected to the Ooler app (only one Bluetooth connection is allowed at a time). You may need to hold the power button for a few seconds to make it discoverable.
4. Confirm the device and the integration will verify the connection.

If the BLE connection needs to be re-verified later, use the Reconfigure option in the integration's settings (Settings -> Devices & Services -> Ooler -> Configure).

### Known limitations

- **One Bluetooth connection at a time.** The Ooler only supports a single BLE connection. If the Ooler app is connected, HA cannot connect (and vice versa). Use the Bluetooth Connection switch to disconnect from HA when you need the app.
- **ESP32 proxy connection slots.** Each Ooler uses 4 BLE notification slots. ESPHome proxies provide 12 slots (vs 9 for raw ESP-IDF). If you have multiple BLE devices on one proxy, you may run into slot limits.
- **No Wi-Fi or cloud support.** The Ooler communicates only via Bluetooth. The device must be within BLE range of your HA server or an ESPHome Bluetooth proxy.

### Troubleshooting

- **Device not discovered:** Ensure the Ooler is powered on and not connected to the mobile app. Hold the power button for ~5 seconds to enter pairing/discoverable mode.
- **Frequent disconnects:** Check your ESP32 proxy's BLE slot usage. Reduce the number of active BLE connections if needed. Ensure the proxy is running ESPHome (not raw ESP-IDF) for maximum notification slots.
- **Temperature displays incorrectly:** The integration auto-syncs the Ooler's display unit to your HA unit system. If you recently changed your HA unit system, restart the integration.
- **"Device unavailable" after HA restart:** The integration seeds the BLE device from HA's cache on startup. If the proxy hasn't reported the device yet, it may take up to 60 seconds for the periodic reconnect to establish the connection.
- **Missed notifications (proxy flakiness):** If you see "poll detected missed notifications" in logs, the integration is handling it automatically. Check device diagnostics for subscription mismatch and forced reconnect counts. Consider dedicating a proxy to BLE-heavy devices if this happens frequently.
- **Diagnostics:** Download device diagnostics from Settings -> Devices -> Ooler -> Download diagnostics. This includes connection state, device settings, sensor values, and proxy reliability metrics for debugging.

### Example automations

**Turn on the Ooler at bedtime:**
```yaml
automation:
  - alias: "Ooler bedtime cooling"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: climate.set_temperature
        target:
          entity_id: climate.ooler_92106080601
        data:
          temperature: 68
      - service: climate.turn_on
        target:
          entity_id: climate.ooler_92106080601
```

**Turn off in the morning:**
```yaml
automation:
  - alias: "Ooler morning off"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: climate.turn_off
        target:
          entity_id: climate.ooler_92106080601
```

**Disconnect for Ooler app access:**
```yaml
automation:
  - alias: "Ooler disconnect for app"
    trigger:
      - platform: state
        entity_id: input_boolean.ooler_app_mode
        to: "on"
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.ooler_92106080601_bluetooth_connection
```

**Boost mode during hot nights:**
```yaml
automation:
  - alias: "Ooler boost when hot"
    trigger:
      - platform: numeric_state
        entity_id: sensor.bedroom_temperature
        above: 78
    action:
      - service: climate.set_fan_mode
        target:
          entity_id: climate.ooler_92106080601
        data:
          fan_mode: "Boost"
```

## Contributions are welcome!

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)

## Credits

The code for this integration was primarily based on the official [EufyLife integration](https://www.home-assistant.io/integrations/eufylife_ble/) and then adjusted using other components like [Snooz](https://www.home-assistant.io/integrations/snooz/) and [Philips Hue](https://www.home-assistant.io/integrations/hue/) as guides.

This readme and some supporting HACS elements were generated from [@oncleben31](https://github.com/oncleben31)'s [Home Assistant Custom Component Cookiecutter](https://github.com/oncleben31/cookiecutter-homeassistant-custom-component) template.

Development of this integration is assisted by [Claude Code](https://claude.ai/claude-code) (Anthropic). Claude is used as a development tool for code generation, testing, and analysis. All code changes are reviewed, tested, and approved by the maintainer before being merged.

---

[integration_blueprint]: https://github.com/custom-components/integration_blueprint
[ruff]: https://github.com/astral-sh/ruff
[ruff-shield]: https://img.shields.io/badge/code%20style-ruff-000000.svg?style=for-the-badge
[buymecoffee]: https://www.buymeacoffee.com/PostLogical
[buymecoffeebadge]: https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=for-the-badge
[commits-shield]: https://img.shields.io/github/commit-activity/y/PostLogical/ooler.svg?style=for-the-badge
[commits]: https://github.com/PostLogical/ooler/commits/master
[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[discord]: https://discord.gg/Qa5fW2R
[discord-shield]: https://img.shields.io/discord/330944238910963714.svg?style=for-the-badge
[oolerlogo]: logo@2x.png
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=for-the-badge
[forum]: https://community.home-assistant.io/
[license-shield]: https://img.shields.io/github/license/PostLogical/ooler.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-%40PostLogical-blue.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/PostLogical/ooler.svg?style=for-the-badge
[releases]: https://github.com/PostLogical/ooler/releases
[user_profile]: https://github.com/PostLogical
[my-badge]: https://my.home-assistant.io/badges/hacs_repository.svg
[my-link]: https://my.home-assistant.io/redirect/hacs_repository/?owner=PostLogical&repository=ooler&category=integration
