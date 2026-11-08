## What's Changed in v1.12.0

This release brings the integration to the Home Assistant **Platinum** quality
level and adds optional automatic tracking of new clients. It makes PoE
switching work on more controllers, keeps device and site entities available
on controllers without internet access, fixes device names of tracked clients
and network devices, and cleans up logging and error messages.

### Added

- **Optional client auto-discovery** (#88, #111, PR #89). Presence-only device
  trackers for new clients, off by default, with SSID, wired, guest,
  private-MAC, name and denylist filters and configurable registry retention.
  Offline auto trackers keep their names, and private MAC addresses are
  excluded by default.

### Fixed

- **PoE switching on controllers that reject the PoE endpoints** (#81, PR #114
  by @lkostrowski, PR #171 by @sergedornseiffer). The integration now falls
  back to updating the port itself and leaves its VLAN, speed and name
  unchanged. This helps controllers that reject the PoE endpoints, for example
  with Agile Series switches, and includes controller software 6.3.0.111,
  which requires the port name in that update.
- **Device and site entities went unavailable after ~30 minutes** on
  controllers without internet access (#159, reported by @rloipfinger). The
  firmware update check timed out and failed every following poll until a
  reload. A timeout now only skips that check until the next one 30 minutes
  later; all other data keeps updating.
- **Device tracker warning in Home Assistant 2026.11** (#148, PR #150 by
  @hmmbob). Network device trackers now provide their device information, so
  Home Assistant no longer warns that this will stop working in 2028.11.
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
  name. Existing entity IDs are kept. The switch also follows the controller
  setting (#113).
- **Clients missing on some software controllers** (PR #122 by @ot316).
  Clients are listed via the v1 endpoint on controllers without the v2
  clients endpoint.
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

**Full Changelog**: https://github.com/bullitt186/ha-omada-open-api/compare/v1.11.1...v1.12.0
