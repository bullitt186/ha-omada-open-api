# Agent Instructions - Home Assistant Integration Development

## Overview
This project is a Home Assistant integration for TP-Link Omada SDN using the Open API.

**Purpose**: Provide information retrieved via the Omada Open API as entities within Home Assistant, enabling monitoring and control of Omada SDN infrastructure (controllers, access points, switches, gateways, and clients).

## Documentation References

### CRITICAL: Documentation Hierarchy
**ALWAYS** consult official documentation before making any changes:

1. **Home Assistant Developer Documentation**
   - Use GitHub MCP tool to search: `home-assistant/developers.home-assistant`
   - Authoritative source for: Integration patterns, best practices, quality standards, entity types, config flows, etc.
   - **MUST** be followed strictly for all HA integration development

2. **HACS Publishing Documentation**
   - Use GitHub MCP tool to search: `hacs/documentation` (specifically `source/docs/publish/`)
   - Authoritative source for: HACS requirements, repository structure, validation, publishing workflow
   - **MUST** be followed strictly when preparing for HACS publication

3. **Omada Open API Documentation**
   - **Official Documentation**: https://use1-omada-northbound.tplinkcloud.com/doc.html#/home
   - **OpenAPI Specification**: `/workspaces/ha-omada-open-api/openapi/openapi.json` (complete Swagger/OpenAPI spec)
   - Authoritative source for: All endpoint definitions, parameters, request/response schemas, data models

**When there are doubts or questions**:
- **Home Assistant patterns**: Search `home-assistant/developers.home-assistant` FIRST
- **HACS requirements**: Search `hacs/documentation` (source/docs/publish/) FIRST
- **Omada API**: Consult `openapi/openapi.json` FIRST

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
- **Pagination Requirements**:
  - ALL list-type endpoints (sites, devices, clients, applications, etc.) REQUIRE pagination parameters `pageSize` and `page` in the query string
  - Omitting these parameters results in 400 Bad Request errors
  - **Multi-Page Fetching**: Even with `pageSize=1000`, you may need to fetch multiple pages. Always check `totalRows` in the response and implement a loop to fetch all pages
  - Example: Applications endpoint returned 2467 total items across 3 pages with pageSize=1000
  - Implement pagination loop:
    ```python
    all_items = []
    page = 1
    while True:
        result = await fetch_page(page, pageSize=1000)
        items = result["result"]["data"]
        total = result["result"]["totalRows"]
        all_items.extend(items)
        if len(all_items) >= total or len(items) < pageSize:
            break
        page += 1
    ```

### Data Models
- **Controllers**: Omada controller information and status
- **Sites**: Network sites with configuration and device lists
- **Access Points**: WiFi AP status, clients, channel, signal strength
- **Switches**: Port status, PoE usage, client connections
- **Gateways**: WAN/LAN status, traffic statistics, VPN connections
- **Clients**: Connected devices with MAC, IP, signal strength, traffic
- **Applications**: DPI-tracked applications with traffic data
  - Field structure: `{"application": "app-name", "applicationId": 123, "family": "Category", "description": "..."}`
  - **CRITICAL**: Use `application` for name (NOT `applicationName`, `name`, or `appName`)
  - **CRITICAL**: Use `family` for category (NOT `familyName` or `category`)
  - Requires DPI (Deep Packet Inspection) enabled on gateway
  - Per-client traffic data available via `/dashboard/specificClientInfo/{clientMac}` endpoint

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
CONF_SELECTED_CLIENTS = "selected_clients"
CONF_SELECTED_APPLICATIONS = "selected_applications"
CONF_CONTROLLER_TYPE = "controller_type"

# Use in tests
from custom_components.omada_open_api.const import CONF_ACCESS_TOKEN
```

### Translation Files & UI Strings
**CRITICAL**: For proper UI display in config/options flows:
1. **strings.json**: Primary translation file with all user-facing text
2. **translations/en.json**: Required copy of strings.json for runtime translations
3. Both files must be identical and kept in sync

**Options Flow Menu Structure:**
```json
{
  "options": {
    "step": {
      "init": {
        "title": "Configuration Options Title",
        "menu_options": {
          "option_key_1": "Display Name for Option 1",
          "option_key_2": "Display Name for Option 2"
        }
      },
      "option_key_1": {
        "title": "Option 1 Form Title",
        "description": "Detailed description...",
        "data": {
          "field_name": "Field Label"
        }
      }
    }
  }
}
```

**Creating Translation Files:**
```bash
# After editing strings.json, always copy to translations/
mkdir -p custom_components/omada_open_api/translations
cp custom_components/omada_open_api/strings.json \
   custom_components/omada_open_api/translations/en.json
```

### Debugging API Response Structures
When uncertain about API field names or response structure:
1. **JSON Dump Approach** (when logging doesn't work):
   ```python
   import json
   with open("/tmp/debug_response.json", "w") as f:
       json.dump(api_response, f, indent=2)
   _LOGGER.warning("DEBUG: Response dumped to /tmp/debug_response.json")
   ```
2. User can then `cat /tmp/debug_response.json` to inspect exact structure
3. **Remove debug code** before final commit
4. This is more reliable than logging when dealing with complex nested structures

### Application Traffic Tracking Implementation
**Complete implementation** for per-client application traffic monitoring:

**API Endpoints:**
```python
# Get all applications (requires pagination)
GET /openapi/v1/{omadacId}/sites/{siteId}/applicationControl/applications
Params: {"page": 1, "pageSize": 1000}

# Get client app traffic
GET /openapi/v1/{omadacId}/sites/{siteId}/dashboard/specificClientInfo/{clientMac}
Params: {"startTime": timestamp_ms, "endTime": timestamp_ms}
```

**Coordinator Pattern:**
```python
class OmadaAppTrafficCoordinator(DataUpdateCoordinator):
    """Coordinator for application traffic data with midnight reset."""

    def __init__(self, ...):
        self._last_reset = dt_util.start_of_local_day(dt_util.now())

    async def _async_update_data(self):
        """Fetch data from midnight to now, reset at midnight."""
        now = dt_util.now()
        today_start = dt_util.start_of_local_day(now)

        # Check if day has changed
        if today_start > self._last_reset:
            self._last_reset = today_start
            # Data will reset automatically as we fetch from new midnight
```

**Sensor Auto-Scaling:**
```python
def _auto_scale_bytes(bytes_value: int) -> tuple[float, str]:
    """Auto-scale bytes to appropriate unit (B, KB, MB, GB, TB)."""
    if bytes_value < 1024:
        return (float(bytes_value), "B")
    elif bytes_value < 1024**2:
        return (bytes_value / 1024, "KB")
    elif bytes_value < 1024**3:
        return (bytes_value / 1024**2, "MB")
    elif bytes_value < 1024**4:
        return (bytes_value / 1024**3, "GB")
    else:
        return (bytes_value / 1024**4, "TB")
```

**Config Flow Integration:**
- Add application selection step after client selection
- Fetch all applications with pagination loop
- Store selected application IDs in config entry
- Provide options flow menu for modifying selections
- Link sensors to client devices via device_info

## README Best Practices for HACS Integrations

### Structure and Workflow

#### 1. Title & Badges
- Use a descriptive integration name matching the domain and pair it with a concise tagline. Include a small logo or banner if available. Place badges relevant to Home Assistant integrations—such as HACS status, release version, build status and licence—to make the project state transparent. Consider adding badges for test coverage or code quality if you run automated workflows.
- Link to the GitHub release page and add a My Home Assistant button that opens a direct installation link. This button lets users install the integration in one click when they are logged into Home Assistant.

#### 2. Integration Description & Motivation
- Explain in a few sentences what the integration does, which devices or services it integrates and why it exists. A "Why?" section can help convey the benefit.
- Describe the target audience (Home Assistant users) and main use cases (e.g. monitoring sensors, controlling devices).

#### 3. Table of Contents
- Generate a table of contents with links to all sections. HACS integration readmes can be lengthy, so navigation links help users find installation or configuration quickly.

#### 4. Installation & Setup

**HACS Installation (Recommended):**
- Clarify that users need to have HACS installed in their Home Assistant instance and provide a link to the HACS setup guide.
- If the repository is not part of the default HACS store, instruct users to:
  1. Open HACS → Integrations
  2. Choose Custom repositories
  3. Enter the repository URL
  4. Set the category to Integration
- After adding the repository, they should search for the integration in HACS, click Install and allow Home Assistant to restart if prompted.
- Finally, instruct them to go to Settings → Devices & Services, click Add Integration, search for the integration name and follow the on‑screen configuration flow.

**Manual Installation:**
- Provide fallback instructions for users who do not use HACS.
- Ask them to download the latest release archive or clone the repository, then copy the integration folder (matching the domain) into the `custom_components` directory of their Home Assistant configuration.
- After copying the files, they must restart Home Assistant and add the integration via Settings → Devices & Services.
- If the integration supports YAML configuration only, include a full configuration example and explain each parameter.

**Quick-Start Example:**
- In both cases, offer a quick‑start example showing the minimal steps required to see the integration working.
- Use UI screenshots or YAML snippets to demonstrate the first sensor or entity being created.

#### 5. Configuration
- Describe whether configuration is performed through the UI (config flow) or via `configuration.yaml`.
- List and explain the fields presented during setup (API keys, hostnames, tokens, prefixes, filters).
- Include an example `configuration.yaml` snippet for YAML‑based configuration, documenting required and optional parameters along with their data types and purposes.
- If external credentials or API keys are needed, explain how to obtain them and note any network ports or firewall rules.

#### 6. Usage & Examples
- Provide examples of how the integration appears in Home Assistant: show typical sensors or controls, and demonstrate automations that use the integration.
- Use YAML or automation snippets as examples.
- Document available services, events and options in clear lists or tables. For example, list service calls with parameters, or event names fired by the integration.
- Include recipes or use cases for deeper usage, such as automating tasks based on sensor values.

#### 7. Feature Overview & Philosophy
- Summarize the core features your integration offers (platforms implemented, supported devices, sensors or services).
- Highlight unique benefits, such as local control, energy efficiency or advanced filtering.
- Include a brief design philosophy explaining architectural choices or trade‑offs (e.g. asynchronous I/O, remote API usage).

#### 8. Repository Structure & Metadata
- Explain that the repository must include a valid `manifest.json` and `hacs.json` at the appropriate locations; these files define the domain, integration version, documentation URL, codeowners and other metadata required by HACS.
- Developers should also register the integration's brand (icon and metadata) in the `home‑assistant/brands` repository before submitting to the community store.
- Highlight that once the integration is accepted into the HACS default store, you can add a HACS badge to the README to signal its availability.
- Include the My Home Assistant button to allow one‑click installation directly from Home Assistant.
- Advise that the project should have at least one GitHub release, a descriptive repository description, a LICENSE file and a CHANGELOG.md.
- A CONTRIBUTING.md file and GitHub Actions for linting/testing further enhance credibility.

#### 9. Troubleshooting & Known Issues

**Common Problems:**
- **Integration not loading**: Check Home Assistant logs and validate that the `manifest.json` and `hacs.json` files are present and syntactically correct.
- **HACS submission rejected**: Ensure that the integration's brand is registered, the repository structure follows HACS guidelines and all mandatory files (manifest, hacs.json, licence) are present.
- **Authentication or connection errors**: Verify credentials, API keys and network ports, and mention firewall configuration where relevant.
- List any known limitations or unsupported features, such as unsupported network modes or missing proxy support.
- Encourage users to report issues via GitHub or the community forum.

#### 10. Further Information
- Link to the Home Assistant developer documentation, HACS documentation and any API or device documentation relevant to your integration.
- Provide references to external resources such as templates, examples or community forum posts for advanced usage.

#### 11. Community & Contribution
- Encourage users to open issues, propose features or submit pull requests.
- Reference a separate CONTRIBUTING.md file and the code of conduct.
- Mention communication channels such as GitHub Discussions, the Home Assistant community forum or Discord for support and collaboration.

#### 12. Licence & Legal
- State the licence of the project and link to the LICENSE file.
- Add acknowledgments or notes about third‑party libraries where appropriate.

### Notes for README Creation
- **Customization**: Adapt this template to the specific requirements of the project. The more complex the project, the more detailed the examples and explanations should be.
- **Mark Assumptions**: If required details are missing (e.g., licence or target audience), clearly mark your assumptions and actively request a verification step.
- **Currency**: Ensure that version notes and documentation links are up to date. Check releases regularly.
- **Language & Style**: Use clear, precise language; emphasize keywords in bold; structure sections logically. Use English for code and specifications.
