# Ooler

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

[![pre-commit][pre-commit-shield]][pre-commit]
[![Black][black-shield]][black]

[![hacs][hacsbadge]][hacs]
[![Project Maintenance][maintenance-shield]][user_profile]
[![BuyMeCoffee][buymecoffeebadge]][buymecoffee]

[![Discord][discord-shield]][discord]
[![Community Forum][forum-shield]][forum]

This custom Home Assistant component controls your Ooler Sleep System over a Bluetooth connection. It is fully compatible with ESPHome Bluetooth Proxies, so if your server is not in range of your Ooler, you can set up an ESP32 in your bedroom to relay the connection.

**This component will set up the following platforms.**

| Platform  | Description                                                                |
| --------- | -------------------------------------------------------------------------- |
| `climate` | Show current Ooler settings and control power, fan speed, and temperature. |
| `sensor`  | Show water level.                                                          |
| `switch`  | Switch cleaning mode or Bluetooth connection on or off.                    |

### Temperature units

The integration automatically syncs the Ooler's temperature unit to match your Home Assistant unit system (metric = °C, imperial = °F). This ensures temperatures are displayed correctly in both HA and on the Ooler's physical display. If you need a different unit on the device, please [open an issue](https://github.com/PostLogical/ooler/issues).

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
| Water level | `sensor` | Current (very rough) water reservoir level (%) - 0%, 50%, or 100% |
| Cleaning mode | `switch` | Start/stop UV cleaning cycle |
| Bluetooth connection | `switch` | Manually disconnect to free the connection for the Ooler app |

### Data updates

The integration maintains a persistent BLE GATT connection to each Ooler device. State updates (power, temperature, mode) are pushed in real-time via GATT notifications. Water level and cleaning status are polled every 5 minutes.

If the connection drops, the integration reconnects automatically — both immediately on disconnect and via a 60-second periodic fallback. When multiple devices reconnect simultaneously (e.g., after a proxy restart), attempts are staggered to avoid overwhelming the proxy's connection slots.

![oolerlogo][oolerlogo]

## Installation

### HACS

1. Find the integration as `Ooler`
2. Click install.
3. Restart Home Assistant.

### Manual

1. Copy the `custom_components/ooler/` folder to your HA `custom_components/` directory.
2. Restart Home Assistant.

## Setup

1. In the HA UI go to "Settings" -> "Devices & Services" -> "Integrations".
2. Your Ooler should appear in the discovered integrations automatically. You can also click the + sign and search for "Ooler".
3. If your Ooler is not discovered, make sure it is powered on and not connected to the Ooler app (only one Bluetooth connection is allowed at a time). You may need to hold the power button for a few seconds to make it discoverable.
4. Confirm the device and the integration will verify the connection.

### Known limitations

- **One Bluetooth connection at a time.** The Ooler only supports a single BLE connection. If the Ooler app is connected, HA cannot connect (and vice versa). Use the Bluetooth Connection switch to disconnect from HA when you need the app.
- **ESP32 proxy connection slots.** Each Ooler uses 4 BLE notification slots. ESPHome proxies provide 12 slots (vs 9 for raw ESP-IDF). If you have multiple BLE devices on one proxy, you may run into slot limits.
- **No Wi-Fi or cloud support.** The Ooler communicates only via Bluetooth. The device must be within BLE range of your HA server or an ESPHome Bluetooth proxy.

### Troubleshooting

- **Device not discovered:** Ensure the Ooler is powered on and not connected to the mobile app. Hold the power button for ~5 seconds to enter pairing/discoverable mode.
- **Frequent disconnects:** Check your ESP32 proxy's BLE slot usage. Reduce the number of active BLE connections if needed. Ensure the proxy is running ESPHome (not raw ESP-IDF) for maximum notification slots.
- **Temperature displays incorrectly:** The integration auto-syncs the Ooler's display unit to your HA unit system. If you recently changed your HA unit system, restart the integration.
- **"Device unavailable" after HA restart:** The integration seeds the BLE device from HA's cache on startup. If the proxy hasn't reported the device yet, it may take up to 60 seconds for the periodic reconnect to establish the connection.
- **Diagnostics:** Download device diagnostics from Settings -> Devices -> Ooler -> Download diagnostics. This includes connection state, device settings, and sensor values for debugging.

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

## Contributions are welcome!

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)

## Credits

The code for this integration was primarily based on the official [EufyLife integration](https://www.home-assistant.io/integrations/eufylife_ble/) and then adjusted using other components like [Snooz](https://www.home-assistant.io/integrations/snooz/) and [Philips Hue](https://www.home-assistant.io/integrations/hue/) as guides.

This readme and some supporting HACS elements were generated from [@oncleben31](https://github.com/oncleben31)'s [Home Assistant Custom Component Cookiecutter](https://github.com/oncleben31/cookiecutter-homeassistant-custom-component) template.

---

[integration_blueprint]: https://github.com/custom-components/integration_blueprint
[black]: https://github.com/psf/black
[black-shield]: https://img.shields.io/badge/code%20style-black-000000.svg?style=for-the-badge
[buymecoffee]: https://www.buymeacoffee.com/PostLogical
[buymecoffeebadge]: https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=for-the-badge
[commits-shield]: https://img.shields.io/github/commit-activity/y/PostLogical/ooler.svg?style=for-the-badge
[commits]: https://github.com/PostLogical/ooler/commits/main
[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[discord]: https://discord.gg/Qa5fW2R
[discord-shield]: https://img.shields.io/discord/330944238910963714.svg?style=for-the-badge
[oolerlogo]: logo@2x.png
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=for-the-badge
[forum]: https://community.home-assistant.io/
[license-shield]: https://img.shields.io/github/license/PostLogical/ooler.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-%40PostLogical-blue.svg?style=for-the-badge
[pre-commit]: https://github.com/pre-commit/pre-commit
[pre-commit-shield]: https://img.shields.io/badge/pre--commit-enabled-brightgreen?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/PostLogical/ooler.svg?style=for-the-badge
[releases]: https://github.com/PostLogical/ooler/releases
[user_profile]: https://github.com/PostLogical
