## What's Changed in v1.12.0b1

> **Beta release:** HACS offers this version only when beta versions are
> enabled for this repository. Please report unexpected entity growth,
> filtering behavior, or registry cleanup before the stable release.

This beta adds opt-in, presence-only client auto-discovery for installations
that need lightweight tracking without manually selecting every client.

### Added

- **Optional automatic client presence trackers** (#88, #111, PR #89).
  Discovery is off by default and reuses the controller's existing client
  snapshots without additional API requests. Manually selected clients keep
  their existing IDs, sensors, controls, and priority.
- **Discovery filters for large networks.** Limit wireless clients by SSID,
  include or exclude wired and guest clients, exclude locally administered
  private MAC addresses or unnamed clients, and maintain an explicit MAC
  denylist. Signal metrics remain attributes rather than extra entities.
- **Safe, configurable registry retention.** Automatically created trackers
  persist their last successful sighting and can be removed after 0–3650
  days (30 by default; 0 disables deletion). Cleanup runs only after complete
  successful client polls, removes only integration-owned trackers, protects
  manually selected clients, and retains devices with other entities.

### Beta testing requested

- Verify expected tracker counts before and after enabling discovery.
- Exercise SSID, wired, guest, private-MAC, name, and explicit-exclusion
  filters on larger installations.
- Confirm absent clients remain away until retention expires and that API
  failures never trigger cleanup.

**Full Changelog**: https://github.com/bullitt186/ha-omada-open-api/compare/v1.11.1...v1.12.0b1
