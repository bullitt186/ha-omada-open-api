# TP-Link Omada SDN Integration for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/bullitt186/ha-omada-open-api.svg?style=for-the-badge)](https://github.com/bullitt186/ha-omada-open-api/releases)
[![License](https://img.shields.io/github/license/bullitt186/ha-omada-open-api.svg?style=for-the-badge)](LICENSE)
[![Code Quality](https://img.shields.io/badge/code%20quality-A+-brightgreen?style=for-the-badge)](https://github.com/bullitt186/ha-omada-open-api)

**Monitor and control your TP-Link Omada SDN infrastructure directly from Home Assistant.**

[![My Home Assistant](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=omada_open_api)

---

## ⚠️ **DISCLAIMER**

**This integration is currently a work in progress. Please read carefully before using:**

- **🚧 Work in Progress**: This integration is under active development and may contain bugs or incomplete features.
- **🤖 AI-Assisted Development**: This project has been heavily developed with the assistance of AI tools and may not follow all traditional development best practices.
- **🔮 No Long-Term Support Guarantee**: The maintainer cannot guarantee continued support or maintenance of this integration in the medium to long term.
- **⚠️ Use at Your Own Risk**: Users install and use this integration entirely at their own risk. Always test in a non-production environment first.
- **☁️ Cloud Controller Untested**: Omada Cloud Controller support has not been thoroughly tested. Local controller support is the primary focus.

**If you encounter issues or have concerns, please open an issue on GitHub. Contributions and testing feedback are welcome!**

---

## Table of Contents

- [About](#about)
- [Why This Integration?](#why-this-integration)
- [Features](#features)
- [Installation](#installation)
  - [HACS Installation (Recommended)](#hacs-installation-recommended)
  - [Manual Installation](#manual-installation)
- [Configuration](#configuration)
  - [Obtaining API Credentials](#obtaining-api-credentials)
  - [Integration Setup](#integration-setup)
- [Usage & Examples](#usage--examples)
  - [Entities Created](#entities-created)
  - [Automation Examples](#automation-examples)
- [Supported Devices](#supported-devices)
- [Troubleshooting](#troubleshooting)
- [Known Limitations](#known-limitations)
- [Development](#development)
- [Contributing](#contributing)
- [Support](#support)
- [License](#license)

---

## About

This integration provides comprehensive monitoring and control of **TP-Link Omada SDN** (Software Defined Networking) infrastructure through the **Omada Open API**. It connects to your Omada Controller (cloud or local) and exposes network devices, clients, and statistics as Home Assistant entities.

**Target Audience**: Home Assistant users with TP-Link Omada networking equipment who want to:
- Monitor network device status and performance
- Track connected clients across their network
- Create automations based on network events
- View real-time network statistics and bandwidth usage
- Monitor application-level traffic (DPI data)

---

## Why This Integration?

**Comprehensive Network Visibility**: Unlike basic router integrations, this provides deep insights into your entire Omada SDN infrastructure—access points, switches, gateways, and all connected clients.

**Automation Ready**: Create powerful automations based on:
- Device online/offline status
- Client connectivity (presence detection)
- Network bandwidth usage
- Application traffic patterns
- Device performance metrics

**Cloud & Local Support**: Works with both cloud-managed and locally-hosted Omada Controllers via the official Open API.

**OAuth 2.0 Authentication**: Secure authentication with automatic token refresh—set it up once and forget it.

---

## Features

### Device Monitoring
- **Controllers**: Status and site information
- **Access Points**: Client counts, uptime, channel, signal strength
- **Switches**: Port status, PoE usage, uplink information
- **Gateways**: WAN/LAN status, traffic statistics, public IP

### Client Tracking
- **Device Tracker**: Presence detection for selected clients
- **Client Sensors**: IP address, signal strength, connection status, SSID
- **Application Traffic**: Per-client bandwidth usage by application (requires DPI)

### Sensors
- Device uptime, CPU/memory utilization, firmware version
- Client counts per device
- Network statistics (upload/download traffic)
- Link speed and connectivity information

### Binary Sensors
- Device online/offline status

### Platforms Implemented
- ✅ **Sensor**: Comprehensive device and client metrics
- ✅ **Binary Sensor**: Device connectivity status
- ✅ **Device Tracker**: Client presence detection (planned)

---

## Installation

### HACS Installation (Recommended)

**Prerequisites**: [HACS](https://hacs.xyz/) must be installed in your Home Assistant instance.

1. **Add Custom Repository**:
   - Open Home Assistant → **HACS** → **Integrations**
   - Click the three dots in the top right → **Custom repositories**
   - Enter repository URL: `https://github.com/bullitt186/ha-omada-open-api`
   - Category: **Integration**
   - Click **Add**

2. **Install Integration**:
   - Search for "**TP-Link Omada SDN**" in HACS
   - Click **Download**
   - Restart Home Assistant when prompted

3. **Add Integration**:
   - Go to **Settings** → **Devices & Services**
   - Click **Add Integration**
   - Search for "**TP-Link Omada SDN**"
   - Follow the configuration flow

[![My Home Assistant](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=omada_open_api)

### Manual Installation

1. **Download Integration**:
   ```bash
   cd /config
   mkdir -p custom_components
   cd custom_components
   git clone https://github.com/bullitt186/ha-omada-open-api.git omada_open_api
   ```

   Or download the [latest release](https://github.com/bullitt186/ha-omada-open-api/releases) and extract to `custom_components/omada_open_api/`

2. **Restart Home Assistant**

3. **Add Integration**:
   - Go to **Settings** → **Devices & Services**
   - Click **Add Integration**
   - Search for "**TP-Link Omada SDN**"
   - Follow the configuration flow

---

## Configuration

### Obtaining API Credentials

To use this integration, you need **OAuth 2.0 credentials** from TP-Link:

1. Visit the [TP-Link Omada API Portal](https://use1-omada-northbound.tplinkcloud.com/doc.html#/home)
2. Log in with your TP-Link account
3. Navigate to **API Credentials** section
4. Create new OAuth 2.0 credentials:
   - **Client ID**: Your application's client ID
   - **Client Secret**: Your application's client secret
   - **Omada ID**: Your controller's Omada Cloud ID

**Note**: These credentials provide access to your Omada Controller. Keep them secure.

### Integration Setup

The integration uses a **multi-step configuration flow**:

#### Step 1: Controller Type
Choose between:
- **Cloud Controller**: Controller managed via TP-Link cloud
- **Local Controller**: Self-hosted controller with Open API enabled

#### Step 2: Region Selection (Cloud Only)
Select your controller's region:
- US East (use1)
- US West (usw1)
- Europe (eu1)
- Asia Pacific (ap1)

Or provide a custom API URL for local controllers.

#### Step 3: OAuth Credentials
Enter your API credentials:
- **Omada ID**: Your controller's unique identifier
- **Client ID**: OAuth 2.0 client ID
- **Client Secret**: OAuth 2.0 client secret

#### Step 4: Site Selection
Select which Omada sites to monitor (supports multiple sites).

#### Step 5: Client Selection (Optional)
Select specific clients to track for device tracking and detailed monitoring.

#### Step 6: Application Selection (Optional)
Select applications to monitor for per-client traffic analysis (requires DPI enabled on gateway).

### Configuration Example

While this integration uses UI-based configuration (no YAML required), here's what the internal structure looks like:

```yaml
# This is handled automatically by the config flow
# No manual configuration needed
omada_open_api:
  controller_type: cloud
  api_url: https://use1-omada-northbound.tplinkcloud.com
  omada_id: "your-omada-id"
  client_id: "your-client-id"
  client_secret: "your-client-secret"
  sites:
    - "site-id-1"
    - "site-id-2"
  selected_clients:
    - "AA:BB:CC:DD:EE:FF"
  selected_applications:
    - "youtube"
    - "netflix"
```

**Network Requirements**:
- Outbound HTTPS (443) access to TP-Link cloud services (for cloud controllers)
- Local network access to your Omada Controller (for local controllers)
- DPI (Deep Packet Inspection) enabled on gateway (for application traffic monitoring)

---

## Usage & Examples

### Entities Created

Once configured, the integration creates entities for each device and selected client:

#### Device Sensors (per Omada device)
- `sensor.<device_name>_connected_clients` - Number of connected clients
- `sensor.<device_name>_uptime` - Device uptime in seconds
- `sensor.<device_name>_cpu_utilization` - CPU usage percentage
- `sensor.<device_name>_memory_utilization` - Memory usage percentage
- `sensor.<device_name>_model` - Device model
- `sensor.<device_name>_firmware_version` - Current firmware version
- `sensor.<device_name>_device_type` - Device type (AP, Switch, Gateway)
- `sensor.<device_name>_uplink_device` - Connected uplink device name
- `sensor.<device_name>_link_speed` - Uplink connection speed

#### Binary Sensors (per device)
- `binary_sensor.<device_name>_status` - Online/offline status

#### Client Sensors (per selected client)
- `sensor.<client_name>_connection_status` - Connected/Disconnected
- `sensor.<client_name>_ip_address` - Current IP address
- `sensor.<client_name>_signal_strength` - WiFi signal strength (wireless only)
- `sensor.<client_name>_connected_to` - Connected AP/switch/gateway name
- `sensor.<client_name>_ssid` - Connected WiFi network (wireless only)

#### Application Traffic Sensors (per client & app)
- `sensor.<client_name>_<app>_upload` - Upload traffic (auto-scaled: B/KB/MB/GB)
- `sensor.<client_name>_<app>_download` - Download traffic (auto-scaled)

### Automation Examples

#### Notify When Device Goes Offline
```yaml
automation:
  - alias: "Alert on AP Offline"
    trigger:
      - platform: state
        entity_id: binary_sensor.living_room_ap_status
        to: "off"
    action:
      - service: notify.mobile_app
        data:
          title: "Network Alert"
          message: "Living Room AP is offline!"
```

#### Track Family Member Presence
```yaml
automation:
  - alias: "Welcome Home"
    trigger:
      - platform: state
        entity_id: sensor.johns_iphone_connection_status
        to: "Connected"
    action:
      - service: light.turn_on
        target:
          entity_id: light.entrance
```

#### Monitor High Bandwidth Usage
```yaml
automation:
  - alias: "High Streaming Usage Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.living_room_tv_youtube_download
        above: 10
        # Above 10 GB
    action:
      - service: notify.mobile_app
        data:
          message: "High YouTube usage detected on Living Room TV"
```

#### Device Performance Monitoring
```yaml
automation:
  - alias: "High CPU on Switch"
    trigger:
      - platform: numeric_state
        entity_id: sensor.main_switch_cpu_utilization
        above: 80
        for: "00:05:00"
    action:
      - service: persistent_notification.create
        data:
          title: "Performance Alert"
          message: "Main switch CPU usage above 80% for 5 minutes"
```

---

## Supported Devices

This integration supports all TP-Link Omada SDN devices accessible via the Open API:

### Controllers
- ✅ Hardware Controllers (OC200, OC300)
- ✅ Software Controllers (Windows/Linux)
- ✅ Cloud-managed Controllers

### Access Points
- ✅ All Omada WiFi 6/6E/7 Access Points
- ✅ Omada WiFi 5 Access Points
- ✅ EAP series (indoor/outdoor)

### Switches
- ✅ JetStream Managed Switches
- ✅ Smart Managed Switches with Omada support
- ✅ PoE and non-PoE models

### Gateways
- ✅ ER series routers with Omada support
- ✅ SafeStream routers

### Clients
- ✅ Any device connected to the Omada network
- ✅ Wireless and wired clients

**Note**: Device availability depends on your Omada Controller's API access level and firmware version.

---

## Troubleshooting

### Integration Not Loading

**Symptoms**: Integration doesn't appear in Home Assistant or fails to load.

**Solutions**:
1. Check Home Assistant logs: `Settings → System → Logs`
2. Verify `manifest.json` exists in `custom_components/omada_open_api/`
3. Verify `hacs.json` exists in repository root
4. Restart Home Assistant after installation
5. Ensure Home Assistant version ≥ 2024.1.0

### Authentication Errors

**Symptoms**: "Invalid credentials" or "Authentication failed" errors.

**Solutions**:
1. Verify OAuth credentials are correct:
   - Client ID matches exactly
   - Client Secret has no extra spaces
   - Omada ID is correct
2. Check controller accessibility:
   - Cloud: Verify region selection
   - Local: Ensure API URL is correct and accessible
   - Test API endpoint with curl or browser
3. Check firewall rules:
   - Allow outbound HTTPS (443) to TP-Link cloud
   - Allow local network access to controller
4. Try **Reauthentication**:
   - Go to **Settings → Devices & Services**
   - Click on integration → **Configure**
   - Select **Reauthenticate**

### No Entities Created

**Symptoms**: Integration loads but no devices or entities appear.

**Solutions**:
1. Verify site selection during setup
2. Check that devices exist in Omada Controller
3. Ensure API user has proper permissions
4. Check coordinator update logs for errors
5. Try reloading the integration

### Missing Application Traffic Sensors

**Symptoms**: Client sensors appear but no app traffic sensors.

**Solutions**:
1. Enable **DPI** (Deep Packet Inspection) on gateway:
   - Omada Controller → **Gateway** → **Settings** → **DPI**
2. Verify applications are selected during config
3. Ensure clients have recent traffic data
4. Application data updates daily (resets at midnight)

### Entities Showing "Unavailable"

**Symptoms**: Entities exist but show "Unavailable" state.

**Solutions**:
1. Check device is online in Omada Controller
2. Verify API credentials haven't expired
3. Check Home Assistant logs for update errors
4. Increase update interval if rate-limited
5. Restart the integration

### Token Refresh Errors

**Symptoms**: "Token expired" or "Refresh failed" in logs.

**Solutions**:
- **Automatic Handling**: Integration automatically refreshes tokens
- **Manual Fix**: Use reauthentication flow if automatic refresh fails
- **Error -44114**: Refresh token expired - reauthenticate to get fresh tokens

---

## Known Limitations

- **Read-Only**: Currently provides monitoring only (no device control)
- **Polling Interval**: Updates every 60 seconds (configurable in future)
- **DPI Requirement**: Application traffic monitoring requires DPI enabled on gateway
- **Cloud Dependency**: Cloud controllers require internet connectivity
- **API Rate Limits**: Respects TP-Link API rate limits (rarely an issue)
- **Local Controller**: Requires Open API enabled (not available on all firmware versions)

**Planned Features**:
- Device control (reboot, LED toggle)
- Switch port configuration
- Guest network toggle
- PoE control per port
- Custom update intervals

**Report Issues**: Found a bug or limitation? Please [open an issue](https://github.com/bullitt186/ha-omada-open-api/issues).

---

## Development

This project uses VS Code devcontainers for a consistent development environment.

### Prerequisites

- **macOS**: Install [Docker Desktop](https://docs.docker.com/desktop/install/mac-install/)
- **Linux**: Install [Docker Engine](https://docs.docker.com/engine/install/)
- **Windows**: Install [WSL2](https://learn.microsoft.com/en-us/windows/wsl/install) and [Docker Engine](https://docs.docker.com/engine/install/)
- [Visual Studio Code](https://code.visualstudio.com/)
- [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)

### Getting Started

1. Clone this repository:
   ```bash
   git clone https://github.com/bullitt186/ha-omada-open-api.git
   cd ha-omada-open-api
   ```

2. Open in VS Code and reopen in container when prompted

3. The development Home Assistant instance will be available at http://localhost:8123

### Code Quality

This project follows **Home Assistant's official coding standards**:

- ✅ **Ruff** - Primary linter and formatter (88 char lines)
- ✅ **Pylint** - Additional code quality checks
- ✅ **Mypy** - Strict type checking
- ✅ **Pre-commit hooks** - Auto-checks before commit
- ✅ **Full type hints** - All functions must be typed
- ✅ **PEP 8 & PEP 257** compliance

### Development Commands

```bash
# Code quality
ruff format custom_components/         # Format code
ruff check custom_components/          # Lint code
mypy custom_components/omada_open_api/ # Type check
pylint custom_components/omada_open_api/ # Additional checks

# Testing
pytest tests/ -v                       # Run tests
pytest tests/ --cov=custom_components.omada_open_api --cov-report=html # With coverage

# Run Home Assistant
hass -c config                         # Start development instance
```

See [CODING_STANDARDS.md](CODING_STANDARDS.md) for detailed guidelines.

---

## Contributing

Contributions are welcome! Whether it's:

- 🐛 **Bug reports** - Open an issue with reproduction steps
- 💡 **Feature requests** - Describe your use case
- 🔧 **Pull requests** - Submit improvements or fixes
- 📖 **Documentation** - Help improve guides and examples
- 🧪 **Testing** - Test with different Omada setups

### How to Contribute

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Make your changes** following coding standards
4. **Add tests** for new functionality
5. **Ensure all tests pass**: `pytest tests/`
6. **Commit changes**: `git commit -m 'Add amazing feature'`
7. **Push to branch**: `git push origin feature/amazing-feature`
8. **Open a Pull Request**

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and development process.

### Communication Channels

- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: Questions and community support
- **Pull Requests**: Code contributions

---

## Support

### Documentation & Resources

- **Omada Open API Docs**: [TP-Link API Portal](https://use1-omada-northbound.tplinkcloud.com/doc.html#/home)
- **Home Assistant Docs**: [Developer Documentation](https://developers.home-assistant.io/)
- **HACS Docs**: [HACS Documentation](https://hacs.xyz/)
- **OpenAPI Spec**: [openapi/openapi.json](openapi/openapi.json) (complete API schema)

### Getting Help

- **Issues**: [Report bugs or request features](https://github.com/bullitt186/ha-omada-open-api/issues)
- **Discussions**: [Community Q&A](https://github.com/bullitt186/ha-omada-open-api/discussions)
- **Home Assistant Community**: [Community Forum](https://community.home-assistant.io/)

---

## License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

### Acknowledgments

- **Home Assistant Community**: For the excellent integration framework
- **TP-Link**: For providing the Omada Open API
- **HACS**: For simplifying custom component distribution

---

**Made with ❤️ for the Home Assistant community**

[![GitHub stars](https://img.shields.io/github/stars/bullitt186/ha-omada-open-api.svg?style=social)](https://github.com/bullitt186/ha-omada-open-api/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/bullitt186/ha-omada-open-api.svg?style=social)](https://github.com/bullitt186/ha-omada-open-api/network)
