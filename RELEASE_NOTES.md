## What's New in v1.6.1

### Bug Fixes

- Fixed firmware update entities (`update.*_firmware`) never showing "update available," even when the Omada controller had a genuine pending update. The integration relied on a `needUpgrade` field from the device-list API that the real controller never returns, so the actual firmware-check endpoint was never queried. Every device is now checked directly against the real firmware-check endpoint on the existing 30-minute interval — verified against live hardware with an actual firmware install end-to-end, including the in-progress indicator and version updating correctly afterward.
- Fixed `make deploy`'s config-entry reload pointing at a non-existent API path, which caused the reload step to silently 404 after the file copy succeeded.
- Fixed `make deploy` reusing already-imported Python code instead of picking up changes: a config-entry reload re-runs setup on the existing in-memory module and does not re-read files from disk. `make deploy` now restarts Home Assistant so code changes actually take effect.
