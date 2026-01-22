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
- **Pagination Requirements**: ALL list-type endpoints (sites, devices, clients, etc.) REQUIRE pagination parameters `pageSize` and `page` in the query string, even when retrieving all items. Default: `{"pageSize": 100, "page": 1}`. Omitting these parameters results in 400 Bad Request errors.

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

## Code Style & Formatting Standards

### Linting & Formatting Tools
Home Assistant enforces strict [PEP 8](https://peps.python.org/pep-0008/) and [PEP 257](https://peps.python.org/pep-0257/) compliance.

**Required Tools:**
- **Ruff**: Primary linter and formatter (replaces black, isort, flake8)
- **Pylint**: Additional code quality checks
- **Mypy**: Static type checking
- **Pytest**: Unit and integration testing

**Commands:**
```bash
# Format code with ruff
ruff format custom_components/

# Lint code with ruff
ruff check custom_components/

# Type check with mypy
mypy custom_components/omada_open_api/

# Run pylint
pylint custom_components/omada_open_api/

# Run tests
pytest tests/ -v
```

### Code Formatting Rules

**Line Length:** Maximum 88 characters

**String Formatting:**
- Prefer f-strings over `%` or `.format()`
- Exception: Use `%` formatting for logging to avoid formatting when suppressed
```python
# Good
message = f"Device {device_name} is {status}"
_LOGGER.info("Can't connect to %s at %s", device_name, url)

# Bad
message = "{} is {}".format(device_name, status)
_LOGGER.info(f"Can't connect to {device_name}")  # Always formats even if log suppressed
```

**Imports:**
- Must be ordered (handled by ruff)
- Use standard aliases:
  - `voluptuous as vol`
  - `homeassistant.helpers.config_validation as cv`
  - `homeassistant.helpers.device_registry as dr`
  - `homeassistant.helpers.entity_registry as er`
  - `homeassistant.util.dt as dt_util`

**Constants:**
- Constants in UPPER_CASE
- Lists and dictionaries should be alphabetically ordered
- Use constants from `homeassistant.const` when available

### Type Hints Requirements

**All code must be fully typed:**
```python
from typing import Any
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> bool:
    """Set up the sensor platform."""
    coordinator: DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    # ...
    return True
```

**Function Docstrings:**
- Use Google-style docstrings
- Type information in type hints, not docstrings
- Document parameters only when not obvious
```python
def some_method(self, param1: str, param2: str) -> int:
    """Example Google-style docstring.

    Args:
        param1: The first parameter.
        param2: The second parameter.

    Returns:
        An integer result.

    Raises:
        KeyError: If the key doesn't exist.
    """
    return 0
```

### File Headers
Use descriptive docstrings:
```python
"""Support for Omada network sensors."""
```

### Log Messages
- No platform/component name needed (added automatically)
- No period at end (like syslog)
- Never log API keys, tokens, passwords
- Use `_LOGGER.debug` for non-user-facing messages
```python
_LOGGER.error("No route to device: %s", self._resource)
# Results in: "No route to device: 192.168.0.18"
```

### Comments
- Comments should be full sentences and end with a period
- Inline comments sparingly, prefer clear code
- Use type hints instead of type comments

### Async/Await Patterns
- All I/O operations must be async
- Use `asyncio.timeout` instead of `async_timeout` (deprecated)
- Avoid blocking the event loop

### Error Handling
- Use specific exception types
- Prefer `raise from` to specify exception cause
- Handle partial failures gracefully
```python
try:
    result = await api_call()
except ApiError as err:
    raise UpdateFailed(f"Error communicating with API: {err}") from err
```

### Testing Requirements
- Write tests for all new code
- Use pytest fixtures
- Mock external API calls
- Test error conditions
- Use snapshot testing for large outputs when appropriate

```python
async def test_sensor(hass: HomeAssistant) -> None:
    """Test the sensor."""
    # Setup
    entry = MockConfigEntry(domain=DOMAIN)
    # Test
    assert await async_setup_entry(hass, entry, mock_add_entities)
```

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
