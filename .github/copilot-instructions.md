# Agent Instructions - Home Assistant Integration Development

## Overview
This project is a Home Assistant integration for TP-Link Omada SDN using the Open API.

**Purpose**: Provide information retrieved via the Omada Open API as entities within Home Assistant, enabling monitoring and control of Omada SDN infrastructure (controllers, access points, switches, gateways, and clients).

**API Documentation**: https://use1-omada-northbound.tplinkcloud.com/doc.html#/home

**Important**: When there are doubts or questions regarding the Omada Open API (endpoints, authentication flow, data structures, request/response formats, etc.), always consult the official API documentation at the URL above.

## Omada Open API Integration Specifics

### API Architecture
- **Cloud-based API**: Omada Controller accessed via TP-Link cloud infrastructure
- **RESTful API**: Standard REST endpoints for data retrieval and device management
- **Authentication**: OAuth 2.0 flow with access tokens and refresh tokens
- **Base URL**: Region-specific endpoints (e.g., use1-omada-northbound.tplinkcloud.com)

### Authentication & Session Management
- **OAuth Flow**: Implement proper OAuth 2.0 authentication flow
- **Token Management**: Handle access token expiration and automatic refresh
- **Refresh Tokens**: Store and use refresh tokens for long-term authentication
- **Token Storage**: Securely store tokens in Home Assistant's config entry data
- **Session Persistence**: Maintain authenticated session across restarts

### API Access Patterns
- **Controller Discovery**: Retrieve available Omada controllers for the account
- **Site Management**: Access multiple sites under a single controller
- **Device Hierarchy**: Controller → Sites → Devices (APs, Switches, Gateways)
- **Client Information**: Track connected clients across network infrastructure
- **Statistics & Metrics**: Retrieve network statistics, bandwidth usage, client counts

### Data Models
- **Controllers**: Omada controller information and status
- **Sites**: Network sites with configuration and device lists
- **Access Points**: WiFi AP status, clients, channel, signal strength
- **Switches**: Port status, PoE usage, client connections
- **Gateways**: WAN/LAN status, traffic statistics, VPN connections
- **Clients**: Connected devices with MAC, IP, signal strength, traffic

### Entity Types to Implement
- **Sensors**: Device counts, client counts, bandwidth usage, uptime, signal strength
- **Binary Sensors**: Device online/offline status, port status, client connectivity
- **Device Tracker**: Client device tracking across network infrastructure
- **Switches**: PoE port control, guest network enable/disable, LED control
- **Diagnostic Sensors**: Firmware version, controller status, site health

### Rate Limiting & API Etiquette
- **Polling Interval**: Recommended minimum 30-60 seconds between full updates
- **Selective Updates**: Only fetch changed data when possible
- **Batch Requests**: Group API calls to minimize requests
- **Error Backoff**: Implement exponential backoff on API errors
- **Concurrent Limits**: Respect concurrent connection limits

### Data Update Strategy
- **Single Coordinator**: Use one DataUpdateCoordinator per controller/site
- **Hierarchical Updates**: Update controller → sites → devices in sequence
- **Cached Data**: Cache frequently accessed static data (device IDs, names)
- **Delta Updates**: Only update entities with changed states
- **Error Handling**: Gracefully handle partial failures (e.g., one site offline)

### Integration Characteristics
- **Integration Type**: `hub` (provides gateway to multiple devices and sites)
- **IoT Class**: `cloud_polling` (cloud-based API with polling)
- **Config Flow**: Required - authenticate via OAuth, select controller/sites
- **Device Registry**: Each physical device (AP, switch, gateway) as separate device
- **Entity Registry**: Multiple entities per device with unique IDs

## Core Guidelines

### Documentation Reference
- Always reference the official Home Assistant integration developer documentation
- Use the GitHub MCP tool to search the repository: `home-assistant/developers.home-assistant`
- Consult documentation for best practices, patterns, and implementation guidance
- Verify approaches against official examples and guidelines

## Integration Development Principles

### 1. Integration Structure
- **Manifest File** (`manifest.json`): Required for all integrations with domain, name, dependencies, requirements, and integration_type
- **Domain**: Short unique name with characters and underscores (cannot be changed)
- **Integration Type**: Must specify (hub, device, service, helper, etc.)
- **IoT Class**: Specify how device communicates (local_polling, local_push, cloud_polling, cloud_push, etc.)

### 2. File Organization
- `__init__.py`: Component initialization
- `config_flow.py`: UI-based configuration flow (required for new integrations)
- `const.py`: Integration-specific constants
- `coordinator.py`: DataUpdateCoordinator for centralized data fetching
- Platform files: `sensor.py`, `switch.py`, etc. for entity platforms
- `services.yaml`: Service action descriptions

### 3. Architecture Principles
- **Async/Await**: All I/O operations must be asynchronous
- **Config Flow**: UI-based configuration (no YAML configuration)
- **Single API Poll**: Use DataUpdateCoordinator for coordinated polling across all entities
- **Entity Platform**: Create platforms that extend proper base classes
- **Dependency Injection**: Pass API clients and coordinators to entities

### 4. Code Quality Requirements
- **Type Hints**: Required for all functions and methods (Python 3.11+)
- **Code Style**: Follow PEP 8 and Home Assistant coding standards
- **Constants**: Use existing constants from `homeassistant.const` where possible
- **External Libraries**: All API logic must be in separate PyPI packages
- **Voluptuous Schema**: Configuration validation with default parameters in schema

### 5. API Integration Best Practices
- **Third-Party Library**: API-specific code in external PyPI package with pinned versions
- **Async HTTP**: Use `aiohttp` for all HTTP communication
- **Error Handling**: Implement proper error handling and retries
- **Authentication**: Handle token refresh and expiration
- **Rate Limiting**: Respect API rate limits

### 6. Entity & Device Management
- **Entity Registry**: Proper entity registration with unique IDs
- **Device Registry**: Group entities under devices with identifiers
- **Entity Naming**: Follow naming conventions (device name + entity type)
- **Availability**: Set entity availability based on device connection status
- **State Updates**: Update states via coordinator, not individual polling

### 7. Quality Scale Requirements (Minimum Bronze Tier)
- **Integration Quality Scale**: New integrations must meet at least Bronze tier requirements
- **Config Flow**: UI-based configuration required
- **Tests**: Unit tests for business logic, integration tests for setup
- **Documentation**: Complete documentation in manifest
- **Code Review**: Follow all checklist items for code review

### Testing
- Write unit tests for all business logic
- Integration tests for platform setup
- Mock external API calls in tests

### Documentation
- Document all public APIs
- Add inline comments for complex logic
- Maintain README with setup instructions

## Development Workflow
1. Use branches for feature development
2. Test locally before committing
3. Ensure all tests pass
4. Follow semantic commit messages
