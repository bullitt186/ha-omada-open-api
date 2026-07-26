## What's New in v1.8.2

### Bug Fixes

- Devices that were already merged together by the bug fixed in v1.8.1 (multiple access points, switches, or gateways folded into a single Home Assistant device) are now automatically split back into clean, separate devices the next time the integration loads — no manual steps required.
- Manually deleting a merged device from Settings → Devices & Services no longer fails with "Failed to remove device entry, rejected by integration."
