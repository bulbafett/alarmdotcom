# About this fork

A small, conservative fork of [pyalarmdotcom/alarmdotcom](https://github.com/pyalarmdotcom/alarmdotcom) **v3.0.15** that keeps the v3 integration working on current Home Assistant (tested on **2026.11.0**). Upstream maintenance is paused. This fork only fixes breakage; it adds no features beyond one option, and it keeps upstream's `pyalarmdotcomajax==0.5.13` dependency.

If you want new features (cameras, activity events and more), look at [ibasebcast/ha-alarmdotcom](https://github.com/ibasebcast/ha-alarmdotcom), an actively developed derivative built on the v4 rewrite. This fork is for people who want the v3 code they already run, minus the crashes.

Maintained as-is for one household's install. Issues are off; pull requests are welcome.

## Changes from upstream v3.0.15

| Change | Symptom it fixes | Upstream |
|---|---|---|
| Update log uses `self.name` instead of `_friendly_name_internal()` | Every entity fails to set up with `AttributeError` (HA 2026.2+) | #509, #540, #545, #549, #552; PRs #514, #519 |
| Options flow no longer assigns `self.config_entry` | Configure (gear) button gives a 500 error (HA 2025.12+) | #506; PR #519 |
| `device_info` is built by keyword, and the partition is linked with `via_device_id` | All platforms fail with `TypeError` (HA 2026.11); `via_device` deprecation warnings (removed in 2027.8) | #558, #510, #525; PR #559 |
| Removed the purge of `device_registry.deleted_devices` | Deprecation warning; breaks in HA 2027.9. HA expires orphaned devices itself | none |
| Lights use `ColorMode` | Lights unavailable (HA 2026.3 removed `COLOR_MODE_*` / `SUPPORT_BRIGHTNESS`) | #524 |
| Reauth updates the existing entry | Re-login after a credential expiry fails with "Unknown error" (HA 2026.5+) | #537; PR #546 |
| New option **Require Code to Arm** (default on, same as v3.0.15) | With a security code set, arming always asked for it | #504; PR #514 |
| `pyalarmdotcomajax_patches.py`: in-memory fixes for the library | Websocket drops on events from unknown devices; reconnect stuck after a token error; first update fails on a list-shaped system response | #524 (traceback), #554 |

The library fixes are applied in memory from `base_device.py`, because Home Assistant installs `pyalarmdotcomajax` from PyPI and its files can't be replaced safely.

## Installing

Not in the HACS / marketplace catalog (the `alarmdotcom` domain belongs to upstream there). Copy `custom_components/alarmdotcom` from a [release tag](../../tags) into your HA `config/custom_components/`, replacing the existing directory, then restart HA. Your existing config entry and entities carry over. If HACS or the marketplace still tracks `pyalarmdotcom/alarmdotcom`, don't update it from there, or it will overwrite this copy.

## Versions

- Branch `v3-fixes`: upstream `v3.0.15` plus the commits above. `master` mirrors upstream untouched.
- Tags `v3.0.15.N`, matching the manifest `version` (sorts above upstream's 3.0.15).
