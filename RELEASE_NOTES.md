## What's New in v1.4.2

### Bug Fixes
- Fixed PoE switch control failing with "General error" (errorCode -1) on all switch ports. The single-port API endpoints (`/ports/{port}/profile-override` and `/ports/{port}/poe-mode`) are broken on many Omada controller firmware versions. Switched to the multi-port batch endpoints (`/multi-ports/profile-override` and `/multi-ports/poe-mode`) which work correctly.

### Improvements
- Improved error messages when PoE control fails — the original API error details are now included in the Home Assistant error notification.
