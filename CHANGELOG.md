# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-02-20

### Fixed
- **Critical**: Fixed automatic token renewal by correcting API parameter placement per Omada Open API specification
  - `_refresh_access_token()`: All parameters (`client_id`, `client_secret`, `refresh_token`, `grant_type`) now correctly sent as query string parameters with no request body
  - `_get_fresh_tokens()`: `omadacId` now correctly sent in JSON body instead of query string
- Added automatic retry logic for expired/invalid token errors (-44112, -44113) and HTTP 401 responses

### Added
- New `_authenticated_request()` wrapper for centralized authentication and retry handling across all API calls
- Extended error code handling: -44111 (invalid grant type) and -44106 (invalid credentials) now trigger automatic client_credentials fallback
- Connection error fallback: Network errors during token refresh now fall back to fresh client_credentials instead of failing
- Open API Access Guide documentation for reference

### Changed
- Extracted `process_client()` and `normalize_client_mac()` into dedicated `clients.py` module
- Extracted `process_device()`, `parse_uptime()`, `format_link_speed()`, `get_device_sort_key()`, and `normalize_site_id()` into dedicated `devices.py` module
- Refactored all 6 API methods to use centralized `_authenticated_request()` wrapper
- Updated `coordinator.py`, `sensor.py`, `binary_sensor.py`, and `__init__.py` to use shared helper modules

## [0.2.0] - 2026-01-25

### Added
- Automatic cleanup of devices when clients are deselected in options flow
- Automatic cleanup of entities when applications are deselected in options flow
- Device registry integration with proper removal of deselected tracked items
- Entity registry integration with cleanup of orphaned application traffic sensors
- MIT License file

### Changed
- Added prominent disclaimer in README about WIP status, AI development, and risks
- Updated README with comprehensive warnings about cloud controller support and stability

### Fixed
- Fixed `KeyError` in `async_unload_entry` when reloading integration via options flow
- Removed incorrect `hass.data[DOMAIN]` access in favor of `entry.runtime_data` pattern
- Devices for deselected clients are now properly removed from device registry
- Entities for deselected applications are now properly removed from entity registry

### Technical Details
- Device cleanup: Compares device identifiers against selected clients/sites lists
- Entity cleanup: Parses app_id from entity unique_id and removes orphaned app traffic sensors
- Both cleanups run automatically before integration reload during options flow changes
- Normalized MAC address and ID comparison (uppercase with hyphens)

## [0.1.0] - 2026-01-25

### Added
- Initial release of TP-Link Omada Open API integration
- OAuth 2.0 authentication with automatic token refresh and renewal
- Support for cloud-based and local Omada controllers
- Multi-site support with configurable site selection
- Device monitoring for Access Points, Switches, and Gateways
- Client device tracking across network infrastructure
- Application traffic tracking with DPI (Deep Packet Inspection)

#### Platforms
- **Sensor Platform**: Device statistics, client counts, bandwidth usage, uptime, signal strength, application traffic
- **Binary Sensor Platform**: Device online/offline status, port status, client connectivity

#### Features
- Comprehensive device information including model, MAC address, IP, firmware version
- Per-device metrics: CPU usage, memory usage, uptime, client counts
- Client tracking: MAC address, IP, hostname, signal strength, connection type
- Application traffic monitoring: Per-client application usage with auto-scaling units
- Automatic data coordinator with configurable update intervals
- Proper device registry integration with manufacturer and model information
- Entity availability tracking based on device connectivity
- Options flow for modifying site, client, and application selections

### Technical Details
- Integration Type: `hub` (provides gateway to multiple devices and sites)
- IoT Class: `cloud_polling` (cloud-based API with polling)
- Config Flow: UI-based configuration with OAuth 2.0 authentication
- Data Update: Coordinated polling with separate coordinators for devices, clients, and application traffic
- Token Management: Automatic refresh with 5-minute expiry buffer, automatic renewal on refresh token expiry

### Requirements
- Home Assistant 2024.1.0 or later
- TP-Link Omada Cloud account or local Omada controller
- OAuth 2.0 credentials (Omada ID, Client ID, Client Secret)
- DPI enabled on gateway for application traffic tracking

[0.3.0]: https://github.com/bullitt186/ha-omada-open-api/releases/tag/v0.3.0
[0.2.0]: https://github.com/bullitt186/ha-omada-open-api/releases/tag/v0.2.0
[0.1.0]: https://github.com/bullitt186/ha-omada-open-api/releases/tag/v0.1.0
