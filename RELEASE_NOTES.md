## What's Changed in v1.12.0b2

> **Beta release:** HACS offers this version only when beta versions are
> enabled for this repository. Please report unexpected entity growth,
> filtering behavior, or registry cleanup before the stable release.

This second beta fixes the findings from the large-installation test of
client auto-discovery and adds several controller compatibility fixes.

### Fixed

- **Auto-discovery cleanup ran off the event loop** (#111). The daily
  cleanup no longer triggers Home Assistant's thread-safety warning.
- **Offline auto trackers lost their name** (#111). Trackers keep the last
  known name, SSID, band, and connection type while offline and across
  restarts instead of falling back to the MAC address. This also fixes
  device names shown as `<MAC> <name>`.
- **Site LED switch showed `unknown`** (#113). The switch now reads the
  site LED setting on every poll and follows changes made in the controller.
- **PoE switching failed with `-1001`** on some controller and switch
  combinations, e.g. JetStream SG2428LP and Agile Series (#81, PR #114 by
  @lkostrowski). The integration falls back to patching only the PoE mode of
  the port, without touching VLAN, speed, or profile settings.
- **Software controllers without the v2 clients endpoint** (e.g. 5.15) no
  longer get stuck in setup retry. Clients are listed via the v1 endpoint
  (PR #122 by @ot316).

### Changed

- **Private MAC addresses are excluded from auto-discovery by default**
  (#111). Randomized MACs rotate and created duplicate trackers. Entries that
  already saved this option keep their choice.
- **Auto trackers expose `mac`, `ip`, and `host_name`** like manually
  selected trackers (#111).

### Still in this beta (from v1.12.0b1)

- Optional, presence-only client auto-discovery (#88, #111, PR #89), off by
  default, with SSID, wired, guest, private-MAC, name, and denylist filters
  and configurable registry retention (30 days by default; 0 keeps entries).

### Beta testing requested

- Confirm offline trackers keep their names after a Home Assistant restart.
- Check whether duplicate trackers still appear with private MACs excluded.
- Confirm expired trackers are removed after the retention period.

**Full Changelog**: https://github.com/bullitt186/ha-omada-open-api/compare/v1.12.0b1...v1.12.0b2
