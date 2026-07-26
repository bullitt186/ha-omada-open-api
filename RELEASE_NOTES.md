## What's New in v1.8.1

### Bug Fixes

- Fixed a bug where Home Assistant could silently merge unrelated Omada devices (access points, switches, gateways, clients) into a single device entry, producing devices with dozens of duplicate or mismatched entities. This was caused by the integration registering a device's IP address as part of its device identity — since IP addresses are reassigned by DHCP over time, this could fold a completely different physical device into an existing one, especially after replacing, renaming, or relocating hardware (e.g. swapping access points between rooms).
- Infrastructure devices (access points, switches, gateways) that are unadopted or removed from the Omada controller are now automatically cleaned up, along with all of their entities. Previously, such devices lingered indefinitely in Home Assistant as "unavailable" until manually deleted.

**Note:** If you were already affected by the device-merging issue before upgrading, the existing merged device will not repair itself automatically — this fix only prevents new merges. Delete the affected device from Settings → Devices & Services after upgrading, and Home Assistant will recreate clean, correctly-separated devices on the next update.
