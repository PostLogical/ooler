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

This custom Home Assistant component will control your Ooler Sleep System over a bluetooth connection. It is fully compatible with ESP Bluetooth Proxies so if your server is not in range of your Ooler, you can set up an ESP-32 in your bedroom to easily connect. At this time it supports turning the Ooler on and off, setting the fan mode, setting the target temperature, starting or stopping cleaning mode, and reading the current status of all of those functions. It also attempts to display the watts currently being used by the device and the current water level; however, both of these seem to be wrong, so further study will be needed to ascertain if those numbers can be gathered. Other functions are not currently implemented, but they would not be hard to develop so feel free to reach out with a request or submit a PR. For some reason the switch entities appear separate from the others at first, but after a while (maybe a reboot), they automatically appear together.

**This component will set up the following platforms.**

| Platform  | Description                                                                |
| --------- | -------------------------------------------------------------------------- |
| `climate` | Show current Ooler settings and control power, fan speed, and temperature. |
| `sensor`  | Show current info on watts used and water level.                           |
| `switch`  | Switch cleaning mode or bluetooth connection on or off.                    |

![oolerlogo][oolerlogo]

## Configuration is done in the UI

1. In the HA UI go to "Settings" -> "Devices & Services" -> "Integrations".
2. If your Ooler is not currently being accessed by an Ooler app and does not have bluetooth turned off entirely, your Ooler should appear in the discovered integrations. However, you can always click the + sign and search for "Ooler" to try to add the integration.
3. If you cannot see any Oolers available, hold the power button on your device for a little over 5 seconds to put it into discoverable mode (you would have to do this during setup anyway and it lasts for 60 seconds each time).
4. Follow the directions to finish pairing and enjoy!
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
