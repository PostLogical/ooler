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

### Setup

Ooler devices are discovered automatically via Bluetooth. During setup, the integration connects to the device and reads its state to verify the connection. No power cycling or pairing button press is required — just confirm the discovered device in the UI.

![oolerlogo][oolerlogo]

## Installation

### HACS (Once available)

1. Find the integration as `Ooler`
2. Click install.
3. Restart Home Assistant.

### Manual

1. Using the tool of choice open the directory (folder) for your HA configuration (where you find `configuration.yaml`).
2. If you do not have a `custom_components` directory (folder) there, you need to create it.
3. In the `custom_components` directory (folder) create a new folder called `ooler`.
4. Download _all_ the files from the `custom_components/ooler/` directory (folder) in this repository.
5. Place the files you downloaded in the new directory (folder) you created.
6. Restart Home Assistant
7. In the HA UI go to "Configuration" -> "Integrations" click "+" and search for "Ooler"

Using your HA configuration directory (folder) as a starting point you should now also have this:

```text
custom_components/ooler/translations/en.json
custom_components/ooler/__init__.py
custom_components/ooler/climate.py
custom_components/ooler/config_flow.py
custom_components/ooler/const.py
custom_components/ooler/manifest.json
custom_components/ooler/models.py
custom_components/ooler/sensor.py
custom_components/ooler/services.yaml
custom_components/ooler/strings.json
custom_components/ooler/switch.py
```

## Configuration is done in the UI

1. In the HA UI go to "Settings" -> "Devices & Services" -> "Integrations".
2. Your Ooler should appear in the discovered integrations automatically. You can also click the + sign and search for "Ooler".
3. If your Ooler is not discovered, make sure it is powered on and not connected to the Ooler app (only one Bluetooth connection is allowed at a time). You may need to hold the power button for a few seconds to make it discoverable.
4. Confirm the device and the integration will verify the connection.
<!---->

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
