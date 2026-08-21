## What's New in v1.10.0

### Features
- Monitor site-to-site, VPN server, and VPN client tunnels from Home Assistant. Each tunnel has a clear connectivity entity, while peer and traffic details are available as diagnostic entities.
- Run a Fusion gateway WAN speed test from Home Assistant and monitor its running state, download, upload, latency, and most recent result.
- Choose whether VPN monitoring and WAN speed-test entities are enabled from the integration's Gateway Entity Settings options.

### Improvements
- VPN client telemetry now reflects the client connection and traffic reported by Omada, instead of presenting peer-count diagnostics that do not apply to VPN clients.
