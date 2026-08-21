## What's New in v1.10.0

### Features
- Monitor site-to-site, VPN server, and VPN client tunnels from Home Assistant. Each tunnel has a clear connectivity entity, while peer and traffic details are available as diagnostic entities.
- Run a Fusion gateway WAN speed test from Home Assistant and monitor its running state, download, upload, latency, and most recent result.
- Choose whether VPN monitoring and WAN speed-test entities are enabled from the integration's Gateway Entity Settings options.

### Improvements
- VPN client telemetry now reflects the client connection and traffic reported by Omada, instead of presenting peer-count diagnostics that do not apply to VPN clients.
- The minimum configurable polling interval is now 30 seconds to protect third-party controller APIs from excessive traffic. Existing lower values are raised automatically during setup.

### Security
- Restored TLS certificate verification for all cloud and traditional OpenAPI connections. Fusion gateways continue to support their dedicated local web session for IP-address and self-signed-certificate compatibility.
- Removed OAuth credentials, access tokens, refresh tokens, and Fusion passwords from reauthentication debug logs and downloaded diagnostics.
- Removed `aiohttp` from the integration manifest because it is already provided and maintained by Home Assistant Core.
