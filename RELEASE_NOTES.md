## What's New in v1.5.0

### Features

- Firmware update entities now use the controller's `needUpgrade` flag as the primary signal for update availability, ensuring the UI immediately shows "Up to date" after a successful firmware upgrade completes
- Firmware info API calls are now only made for devices that actually have an upgrade available, reducing unnecessary API traffic

### Improvements

- Added post-upgrade cooldown polling: after a firmware upgrade finishes, fast polling continues for a few additional cycles to ensure the controller has time to report the new firmware version
- Firmware upgrade progress is now shown immediately in the UI when an upgrade is initiated, without waiting for the next coordinator poll
- Added a safety timeout that clears the "installing" state if the controller never acknowledges the upgrade
- Stale firmware info cache entries are automatically removed when a device no longer needs an upgrade

### Bug Fixes

- Fixed firmware version not updating in the HA UI after a successful firmware upgrade (the update dialog would continue showing an available update even though the device was already on the latest version)
- Fixed upgrade progress indicator not appearing immediately after triggering a firmware update
