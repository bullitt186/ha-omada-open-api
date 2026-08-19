## What's New in v1.9.0

### Features
- Added an on/off LED switch for each access point, so AP status LEDs can be scheduled or toggled from Home Assistant.

### Improvements
- Write-access detection no longer hides PoE, SSID, AP LED, and client-block controls just because the site-wide LED write probe was denied — only the site LED switch is gated by that probe now, so least-privilege API credentials keep the controls that actually work.
- AP radio utilization sensors (Tx/Rx/interference/busy) no longer drop to `unavailable` for most of each polling cycle — their values are now correctly cached and retained between refreshes instead of disappearing until the next fetch.
- Per-band client sensors' `clients` attribute is now populated correctly; it previously stayed empty on every poll even though the sensor's count was accurate.

### Bug Fixes
- Fixed "Modify Client Tracking" and "Modify Application Tracking" failing with a generic error (or silently saving an empty selection) on Fusion (web_session) gateways — these requests now reuse the correct session cookies instead of Home Assistant's shared, cookie-less session.
- Fixed "Modify Client Tracking" showing a `cannot_connect` error on controllers where the clients endpoint returns 404 — it now degrades gracefully instead of raising.
- Fixed a crash ("value must be one of [...]") when filtering tracked clients by SSID after already tracking clients across multiple networks. Filtering also no longer silently untracks clients on other SSIDs when the selection is saved.
