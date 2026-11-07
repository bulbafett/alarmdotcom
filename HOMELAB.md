# Homelab fork

Private fork of [pyalarmdotcom/alarmdotcom](https://github.com/pyalarmdotcom/alarmdotcom), based on upstream tag `v3.0.15` (whose manifest still says 3.0.14). Upstream maintenance is paused; this fork carries the fixes the superduper.ninja Home Assistant needs. Tracked in `bulbafett/homelab#188`.

## Branches and tags

- `homelab`: upstream `v3.0.15` + the commits below. Deploy only from a tag.
- `master`: untouched upstream mirror, for comparing and merging upstream changes if they resume.
- Tags: `v3.0.15-homelab.N`. The manifest `version` matches the tag.

## Changes from upstream v3.0.15

| Change | Why | Upstream |
|---|---|---|
| Update log uses `self.name` | `_friendly_name_internal()` was removed from HA core; every entity setup raised `AttributeError` | #509, PRs #514/#519 (unmerged) |
| Options flow stops assigning `self.config_entry` | Read-only property since HA 2025.12 | PR #519 (unmerged) |
| `device_info` is a property: keyword `DeviceInfo(...)`, parent linked with `via_device_id` | HA 2026.11 rejects a positional dict (all platforms failed to set up, 2026-11-05); the `via_device` tuple is deprecated and removed in 2027.8. The panel/partition device gets no parent | #525 |
| Removed the `deleted_devices` purge in `__init__.py` | `device_registry.deleted_devices` is deprecated, removed in 2027.9, with no public replacement; HA expires orphaned deleted devices itself | none |
| `homelab_pyalarmdotcomajax_patch.py`, applied from `base_device.py` | Two websocket bugs in `pyalarmdotcomajax==0.5.13` (unknown-device messages kill the socket; a token-fetch error leaves the reconnect monitor stuck). Patched in memory: never bind-mount over site-packages | none |
| Removed Dependabot and dependency-review workflows | Noise on a private fork; hassfest is kept | n/a |

## Deploying

See `machines/cerebro/README.md` in `bulbafett/homelab`. In short: cerebro checks out a tag of this repo with a read-only deploy key and bind-mounts `custom_components/alarmdotcom` read-only into the `homeassistant` container. HACS does not manage it.

## Taking a new upstream release

Fetch upstream, merge or rebase its tag onto `homelab`, drop any commit upstream has fixed, update the table above, bump the manifest version and tag `vX.Y.Z-homelab.1`.
