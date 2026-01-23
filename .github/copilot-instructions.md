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
- **OAuth Flow**: OAuth 2.0 Client Credentials grant type (not Authorization Code)
- **Token Lifecycle**: Access tokens expire in 2 hours, refresh tokens in 14 days
- **Automatic Refresh**: Implement 5-minute expiry buffer - refresh tokens before they expire
- **Automatic Renewal**: On refresh token expiry (error -44114), automatically get fresh tokens using client credentials
- **Set-and-Forget**: System automatically renews tokens indefinitely - no user interaction needed after setup
- **Token Storage**: Store in config entry data: `access_token`, `refresh_token`, `token_expires_at` (ISO format)
- **Error Codes**: API returns HTTP 200 with `errorCode: -44114` for expired refresh tokens (not HTTP 401)
- **Session Persistence**: Maintain authenticated session across HA restarts via persisted tokens

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

## Testing Strategy & Best Practices

### Test Organization
Organize tests by functionality into separate files:
- `test_config_flow.py`: Config flow, user input validation, error handling
- `test_api.py`: API client functionality, token management, authentication
- `test_coordinator.py`: Data update coordinator, polling, error recovery
- `test_<platform>.py`: Platform-specific tests (sensors, switches, etc.)

### Incremental Test Development
**CRITICAL**: Add tests incrementally to prevent file corruption and catch issues early:
1. **Add 1-3 related tests** at a time, not entire test suites
2. **Run pytest immediately** after each addition to verify tests pass
3. **Fix any issues** before proceeding to next tests
4. **Commit stable increments** with descriptive messages
5. **Never batch large test additions** - file corruption risk increases significantly

Example workflow:
```bash
# Add 2-3 tests
# Run immediately
pytest tests/test_config_flow.py -v --tb=short
# If passing, commit
git commit -m "test: add error handling tests for config flow"
# Repeat
```

### Test Phases Pattern
Organize comprehensive test suites into phases:
- **Phase 1**: Core functionality (config flow, basic operations)
- **Phase 2**: Advanced features (token management, automatic renewal)
- **Phase 3**: Error handling & edge cases (reauth, failures)
- **Phase 4**: Integration tests (end-to-end scenarios)

Complete each phase before moving to the next.

### Mocking Best Practices
Follow Home Assistant testing patterns:

**Mock via Core Interfaces:**
```python
# Good - mock through HA core
result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})

# Bad - don't instantiate flow directly
flow = OmadaConfigFlow()
```

**Mock External API Calls:**
```python
with patch("aiohttp.ClientSession.post") as mock_post:
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {"errorCode": 0, "result": {...}}
    mock_post.return_value.__aenter__.return_value = mock_response
```

**Mock Config Entry Updates:**
```python
# Use patch.object on hass.config_entries
with patch.object(hass.config_entries, "async_update_entry") as mock_update:
    # Your test code
    mock_update.assert_called_once()
```

**Mock async_setup_entry:**
```python
with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
    # Prevents actual integration loading during config flow tests
```

### Test Fixtures
Create reusable fixtures in `conftest.py`:
```python
@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    entry = MagicMock()
    entry.data = {
        CONF_API_URL: "https://test.example.com",
        CONF_ACCESS_TOKEN: "test_token",
        # ... other required fields
    }
    entry.entry_id = "test_entry_id"
    return entry

@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests."""
    yield  # IMPORTANT: Use yield, not return
```

### Testing Private Methods
When testing private methods is necessary (e.g., `_ensure_valid_token`):
```python
await api_client._ensure_valid_token()  # noqa: SLF001
```
Use `# noqa: SLF001` to suppress ruff's private member access warning.

### DateTime Handling in Tests
Use proper timezone-aware datetime handling:
```python
import datetime as dt

# Good - timezone aware
expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)
iso_string = expires_at.isoformat()

# Bad - naive datetime
expires_at = datetime.now() + timedelta(hours=2)  # Missing timezone
```

### Test Assertions
Be specific and comprehensive:
```python
# Verify flow results
assert result["type"] == FlowResultType.CREATE_ENTRY
assert result["title"] == "Omada - Site Name"
assert result["data"][CONF_ACCESS_TOKEN] == "expected_token"

# Verify API calls
mock_post.assert_called_once()
call_args = mock_post.call_args
assert "/openapi/authorize/token" in call_args[0][0]
assert call_args[1]["params"]["grant_type"] == "client_credentials"

# Verify config entry updates
mock_update.assert_called_once()
updated_data = mock_update.call_args[1]["data"]
assert updated_data[CONF_ACCESS_TOKEN] == "new_token"
```

### Common Testing Patterns

**Config Flow Navigation:**
```python
# User step
result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
assert result["step_id"] == "user"

# Configure next step
result = await hass.config_entries.flow.async_configure(
    result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
)
assert result["step_id"] == "cloud"
```

**Error Testing:**
```python
# Mock error response
mock_response.status = 401
# Or mock exception
mock_post.side_effect = TimeoutError()

# Verify error handling
result = await hass.config_entries.flow.async_configure(...)
assert result["type"] == FlowResultType.FORM
assert "base" in result["errors"]
```

**Multi-Response Mocking:**
```python
# Different responses for sequential calls
mock_post.return_value.__aenter__.side_effect = [
    refresh_error_response,   # First call fails
    fresh_token_response,     # Second call succeeds
]
```

### Test Coverage Goals
- **Config Flow**: All steps, error conditions, user inputs
- **Token Management**: Refresh, renewal, expiry, persistence
- **API Client**: Authentication, API calls, error handling
- **Coordinator**: Data fetching, updates, error recovery
- **Entities**: State updates, availability, attributes

### Running Tests
```bash
# Run specific test file
pytest tests/test_config_flow.py -v --tb=short

# Run specific test
pytest tests/test_api.py::test_token_refresh_before_expiry -v

# Run all tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=custom_components.omada_open_api --cov-report=html
```

## Implementation-Specific Learnings

### OAuth2 Client Credentials Implementation
Current implementation details for Omada Open API:

**Token Endpoints:**
```python
# Get tokens (both initial and renewal)
POST {api_url}/openapi/authorize/token?grant_type=client_credentials
Body: {"omadacId": "...", "client_id": "...", "client_secret": "..."}

# Refresh tokens
POST {api_url}/openapi/authorize/token?grant_type=refresh_token
Body: {"omadacId": "...", "refresh_token": "..."}
```

**Token Response Structure:**
```json
{
  "errorCode": 0,
  "msg": "Success",
  "result": {
    "accessToken": "...",
    "tokenType": "bearer",
    "expiresIn": 7200,
    "refreshToken": "..."
  }
}
```

**Error Code -44114 Handling:**
```python
# Refresh attempt returns this when refresh token expired
{
  "errorCode": -44114,
  "msg": "Refresh token has expired"
}
# Response: Automatically call _get_fresh_tokens() using client credentials
```

### Config Flow Implementation
Multi-step flow structure:
1. **user**: Controller type selection (cloud/local)
2. **cloud**: Region selection (for cloud controllers)
3. **local**: API URL input (for local controllers)
4. **credentials**: OAuth2 credentials input (omada_id, client_id, client_secret)
5. **sites**: Site selection (supports multiple sites)
6. **reauth_confirm**: Reauth flow for credential updates

**Title Formatting:**
- Single site: `"Omada - {site_name}"`
- Multiple sites: `"Omada - {first_site_name} (+{count-1})"`

### API Client Architecture
```python
class OmadaApiClient:
    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api_url: str,
        omada_id: str,
        client_id: str,
        client_secret: str,
        access_token: str,
        refresh_token: str,
        token_expires_at: dt.datetime,
    ) -> None:
        """Initialize with all parameters from config entry."""
        self._token_refresh_lock = asyncio.Lock()  # Prevent concurrent refreshes

    async def _ensure_valid_token(self) -> None:
        """Check token expiry with 5-minute buffer, refresh if needed."""

    async def _refresh_access_token(self) -> None:
        """Refresh using refresh_token, handle -44114 error."""

    async def _get_fresh_tokens(self) -> None:
        """Get fresh tokens using client_credentials."""

    async def _update_config_entry(self) -> None:
        """Persist updated tokens to config entry."""
```

### Constants Management
Proper constant usage:
```python
# From homeassistant.const
from homeassistant.const import CONF_HOST, CONF_VERIFY_SSL

# Integration-specific (in const.py)
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_TOKEN_EXPIRES_AT = "token_expires_at"
CONF_OMADA_ID = "omada_id"
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_API_URL = "api_url"
CONF_SELECTED_SITES = "selected_sites"
CONF_CONTROLLER_TYPE = "controller_type"

# Use in tests
from custom_components.omada_open_api.const import CONF_ACCESS_TOKEN
```
