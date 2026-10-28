## What's Changed in v1.12.0b3

> **Beta release:** HACS offers this version only when beta versions are
> enabled for this repository. Please report problems before the stable
> release.

This third beta brings the integration to the Home Assistant **Platinum**
quality level, fixes device names of tracked clients and network devices,
fixes the site LED switch not appearing on any device, and cleans up logging
and error messages.

### Fixed

- **Device names of tracked clients and network devices** (#111). Selected
  clients showed names like "90:48:6c:… Ring Chime" or "wlan0 Wipro Stilt
  Plug", network devices like "Cinema Ap Cinema Ap", and every entity on
  those devices carried the prefix ("wlan0 SSID"). Devices are now named
  after the Omada client or device name, and trackers use the device name.
  Existing devices are renamed after the update and a restart; names you set
  yourself and entity IDs are kept.
- **"Client signal sensors" option had no effect** (#111). Turning it off
  now stops RSSI, SNR and signal strength sensors from being created.
- **Site LED switch was not attached to any device** (#127). It now appears
  on the site device page under "Configuration". Its name changes from
  "<site> LED" to "LED", because the site device already shows the site
  name. Existing entity IDs are kept.
- **Repeated warnings on every poll** when an optional endpoint keeps
  failing (for example PoE, uplink, SSID overrides, WAN, VPN or application
  traffic). The integration now warns once, logs further failures at debug
  level and logs once when the data is available again.
- **Debug SSID switches action** without a config entry ID only wrote an
  error to the log. It now uses the first loaded Omada integration, as
  documented, and shows a clear error when no integration is loaded or the
  chosen one is not loaded.
- **Client MAC addresses in diagnostics.** The tracked-client and
  auto-discovery exclusion lists in the options are now redacted.

### Changed

- **Home Assistant Platinum quality scale.** The integration now declares
  Platinum, and Home Assistant's validation checks this on every change.
- **Translated error messages.** Errors from buttons, switches, firmware
  updates and setup (for example "controller temporarily unreachable" or
  "authentication failed") are now translatable messages.
- **Setup dialog.** Controller type and cloud region are shown as option
  lists, and every field in the setup and options dialogs has a help text.
- **Fusion gateways** now use Home Assistant's shared HTTP client handling.
  No change in behavior is expected; please report login problems.
- The **Debug SSID switches** action is described in the README and offers a
  picker for the config entry.

### Still in this beta (from v1.12.0b1 and v1.12.0b2)

- Optional, presence-only client auto-discovery (#88, #111, PR #89), off by
  default, with SSID, wired, guest, private-MAC, name and denylist filters
  and configurable registry retention.
- Offline auto trackers keep their names; private MAC addresses are excluded
  from auto-discovery by default (#111).
- Site LED switch follows the controller setting (#113).
- PoE switching fallback for controllers that reject the PoE endpoint with
  `-1001` (#81, PR #114 by @lkostrowski).
- Clients are listed via the v1 endpoint on software controllers without
  the v2 clients endpoint (PR #122 by @ot316).

### Beta testing requested

- Check device and tracker names of selected clients after the update and a
  Home Assistant restart (#111).
- Check that the site LED switch appears on the site device page (#127).
- Fusion gateways: confirm setup and the options dialog still log in.
- Report any warning that still repeats on every poll.

**Full Changelog**: https://github.com/bullitt186/ha-omada-open-api/compare/v1.12.0b2...v1.12.0b3
