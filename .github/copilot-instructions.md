# Integration Quality Scale Compliance

All Copilot changes MUST comply with the Home Assistant Integration Quality Scale as defined in `ha-developer-docs/core/integration-quality-scale` and its linked rules.

- Never introduce changes that would lower the integration’s quality tier or violate any mandatory rule.
- Always aim to raise the integration’s quality tier by:
    - Improving test coverage and reliability.
    - Enhancing user experience, documentation, and diagnostics.
    - Ensuring robust error handling and reauthentication.
    - Refactoring for async operation, strict typing, and code clarity.
    - Supporting translations, logical naming, and discoverability.
- Before making changes, check the current tier and rules in `ha-developer-docs/core/integration-quality-scale/`.
- If a rule or requirement is unclear, consult the linked rule documentation and err on the side of higher quality.
- Document any improvements toward a higher tier in the PR or commit message.
- Never remove or bypass automated tests, diagnostics, or codeowner requirements.
- All new features and refactors must move the integration closer to Gold or Platinum, unless explicitly instructed otherwise.

#### Quality Tiers (Summary)

- **Bronze:** UI config flow, unique entity IDs, automated tests, codeowners, basic docs.
- **Silver:** All Bronze + robust error handling, stable UX, troubleshooting docs, auto recovery.
- **Gold:** All Silver + best UX, auto discovery, translations, diagnostics, >95% test coverage, firmware updates if possible.
- **Platinum:** All Gold + supreme code quality, fully async, strict typing, efficient data handling.
# Agent Instructions - Home Assistant Integration Development

## Overview
This project is a Home Assistant integration for TP-Link Omada Open API.

**Purpose**: Provide information retrieved via the Omada Open API as entities within Home Assistant, enabling monitoring and control of Omada SDN infrastructure (controllers, access points, switches, gateways, and clients).

## Documentation References

### CRITICAL: Documentation Hierarchy
**ALWAYS** consult official documentation in GitHub repos before making any changes:


1. **Home Assistant Developer Documentation (Local)**
    - **Primary Source:** Use the local `ha-developer-docs` folder in this repository as the authoritative source for all Home Assistant integration development details.
    - Covers: Integration patterns, best practices, quality standards, entity types, config flows, and more.
    - **MUST** be followed strictly for all HA integration development.
    - **Note:** This folder is intentionally .gitignored but always present in the dev environment for agent use.

2. **If information is not found in `ha-developer-docs`, fallback to the official GitHub documentation:**
    - Use GitHub MCP tool to search: `home-assistant/developers.home-assistant`
    - Use only if the local docs do not provide the needed details.
    - Covers: Integration patterns, best practices, quality standards, entity types, config flows, etc.
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
- **Home Assistant patterns**: Consult the local `ha-developer-docs` folder FIRST. If not found, search `home-assistant/developers.home-assistant` on GitHub.
- **HACS requirements**: Search `hacs/documentation` (source/docs/publish/) FIRST
- **Omada API**: Consult `openapi/openapi.json` FIRST


**Enforcement**:
- Always consult the local `ha-developer-docs` folder before proposing or implementing changes that touch Home Assistant patterns, config flows, entities, services, or HACS publishing requirements.
- If no relevant documentation is found locally, search the official GitHub documentation as a fallback.
- If still no relevant documentation is found, say so explicitly and continue with best-effort reasoning.

## Omada Open API Integration Specifics

### API Architecture
- **Cloud-based API**: Omada Controller accessed via TP-Link cloud infrastructure
- **RESTful API**: Standard REST endpoints for data retrieval and device management
- **Authentication**: OAuth 2.0 flow with access tokens and refresh tokens
- **Base URL**: Region-specific endpoints (e.g., use1-omada-northbound.tplinkcloud.com)

### Authentication & Session Management

The integration supports two authentication modes via the `OmadaAuthStrategy` pattern (`auth.py`):

#### Traditional OpenAPI (client_credentials)
- **OAuth Flow**: OAuth 2.0 Client Credentials grant type (not Authorization Code)
- **Token Lifecycle**: Access tokens expire in 2 hours, refresh tokens in 14 days
- **Automatic Refresh**: Implement 5-minute expiry buffer - refresh tokens before they expire
- **Automatic Renewal**: On refresh token expiry (error -44114), automatically get fresh tokens using client credentials
- **Set-and-Forget**: System automatically renews tokens indefinitely - no user interaction needed after setup
- **Token Storage**: Store in config entry data: `access_token`, `refresh_token`, `token_expires_at` (ISO format)
- **Error Codes**: API returns HTTP 200 with `errorCode: -44114` for expired refresh tokens (not HTTP 401)
- **Session Persistence**: Maintain authenticated session across HA restarts via persisted tokens

#### Fusion Gateway (web_session)
- **Auth Mode**: Web login via `POST /{omadaCID}/api/v2/login` with username/password
- **Session**: Uses CSRF token + session cookie (no OAuth tokens)
- **Headers**: `Csrf-Token: {token}` + `Omada-Request-Source: web-local` (NOT `Authorization: AccessToken=...`)
- **Cookie Jar**: Requires `aiohttp.CookieJar(unsafe=True)` because Fusion gateways are accessed by IP address and the default safe jar refuses cookies for IP-based URLs
- **Content-Type**: Fusion firmware may return JSON without a Content-Type header — always use `response.json(content_type=None)` when talking to Fusion endpoints
- **CID Auto-Detection**: `GET {url}/api/info` returns `result.omadacId`
- **Single Site**: Fusion gateways typically expose one site with an auto-generated name; use single-site fallback if the stored site_id no longer matches
- **Session Invalidation**: Each web login invalidates prior sessions — never log in twice with the same session; reuse the CSRF token from a single login
- **Entry Data**: Stores `auth_mode: "web_session"`, `username`, `password` (no client_id/secret/tokens)
- **v2 Clients Fallback**: Some Fusion firmware returns error `-1600` on the v2 clients POST endpoint; the client falls back to v1 GET permanently when this occurs

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

**Preferred: use `make` targets** — these encode the correct flags and are kept in sync with CI:

```bash
make test        # Fast: pytest -x -q --tb=short (fail-fast, quiet)
make test-all    # Full suite with coverage + HTML report (-n auto)
make lint        # ruff + pylint
make typecheck   # mypy strict
make coverage    # Full suite + open htmlcov/index.html
make watch       # TDD file-watcher: reruns tests on save (pytest-watch)
make deploy      # copy to /config + restart via localhost:8123 API (devcontainer only)
make check       # Full quality gate: lint + typecheck + test-all (mirrors CI)
make install     # Create .venv and install all dev dependencies
```

Raw commands (use when `make` is not available):
```bash
ruff format custom_components/
ruff check custom_components/
mypy --config-file pyproject.toml custom_components/omada_open_api/
pylint --rcfile=pyproject.toml custom_components/omada_open_api/
pytest tests/ -n auto -v
```

**TDD watch mode:** Run `make watch` in a separate terminal during active development. `pytest-watch` monitors `tests/` and `custom_components/` and instantly reruns failing tests on save — no manual pytest invocations needed during the red→green loop.

**Multi-branch merge tip:** During sequential `git merge --continue` operations, the pre-commit coverage hook runs the full suite on each merge commit. To skip it on intermediate merges and run once at the end:
```bash
SKIP=pytest-coverage git merge --continue   # fast, skips suite
# ... resolve conflicts, continue merges ...
make test-all                                # run full suite once when done
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
2. Test locally before committing (`make test`)
3. Ensure all tests pass (`make check`)
4. Follow semantic commit messages
5. After merging, deploy and verify inside the devcontainer (`make deploy`)

### Agent Environment Notes

Read this before starting any worktree-based or devcontainer-based task — these are
non-obvious environment gotchas discovered the hard way, not things you'll infer from
the code:

- **Git worktrees MUST live at `.worktrees/<name>` inside the repo, never as sibling
  directories** (e.g. never `git worktree add ../ha-omada-open-api-<name>`). Both the
  VS Code devcontainer and the `make devcontainer` compose stack only bind-mount the
  repo root itself — a sibling worktree directory is invisible inside either container.
  `.worktrees/` is already gitignored.
- **Two independent devcontainer entry points exist and don't share state:**
  VS Code's Dev Containers extension launches straight from `devcontainer.json`
  (plain image, no HA instance). `make devcontainer` launches the
  `docker-compose.yml` stack (a `devcontainer` service plus a `homeassistant`
  service with HA on `localhost:8123`). Both provision their own `.venv`
  independently — use whichever one you're already in; you don't need both running.
  (`devcontainer.json` was deliberately reverted from `dockerComposeFile` back to a
  plain `image` in commit `93b54e7` because the compose switch broke VS Code's
  rebuild — don't re-attempt that merge without verifying a full rebuild first.)
- **A host-side `.venv`, if one exists, is not usable.** Its symlinks resolve to
  container-only paths (e.g. `/usr/local/bin/python3.14`) and fail with a bare
  "No such file or directory" on the host. Always run Python tooling (`pytest`,
  `ruff`, `mypy`, `pylint`, `pre-commit`, and therefore `git commit` since
  pre-commit hooks depend on it) via `docker exec <container> ...`, never directly
  on the host.
- **A worktree's `.git` file breaks across host/container path boundaries.** It
  points at a host-absolute gitdir (`<repo>/.git/worktrees/<name>`). If the
  container mounts the repo at a different absolute path than the host does (e.g.
  `/workspaces/ha-omada-open-api` vs `/home/<user>/.../ha-omada-open-api`), git
  commands run inside the container against that worktree fail with "not a git
  repository" until you add a symlink inside the container mapping the host path
  to the container path.

### Deploying and Verifying (devcontainer only)

**IMPORTANT:** All development, deployment, and testing MUST happen inside the devcontainer.
`make deploy` copies files to `/config` and restarts HA via `localhost:8123` so the new
code is actually re-imported. It NEVER writes to any remote host. Never run deploy
targeting `homeassistant.stahmer.lan` or any external HA instance.

**Reload is not enough for code changes:** a config-entry *reload* re-runs setup on the
already-imported Python module in `sys.modules` — it does not re-read the `.py` files
from disk. Copying new files and only reloading the config entry will silently keep
running the old code with no error. Only a full HA restart re-imports the module, which
is why `make deploy` restarts rather than reloads.

After implementing and merging a fix:

1. **Start the devcontainer** (if not already running):
   - In VS Code: reopen in devcontainer
   - In terminal: `make devcontainer` (starts HA on localhost:8123)

2. **Deploy to the local devcontainer HA:**
   ```bash
   make deploy
   ```
   The script copies `custom_components/omada_open_api/` to `/config/custom_components/` and calls the HA REST API at `localhost:8123` to restart Home Assistant (`homeassistant.restart` service), so the new code is re-imported rather than silently reusing the old module. `HASS_TOKEN` is read from `.claude/settings.json`.

3. **Verify entities via MCP** (project-scoped `ha-mcp` in `.claude/settings.json`):
   - Use `mcp__home-assistant__ha_get_state` or `mcp__home-assistant__ha_search_entities`
   - The `ha-mcp` server connects to `localhost:8123` inside the devcontainer

4. **Check HA logs for errors:**
   ```bash
   mcp__home-assistant__ha_get_logs
   ```

### Debugging Live API Responses

When the OpenAPI spec (`openapi/openapi.json`) doesn't match the actual API response, use the inspector script to see the real payload:

```bash
# Set credentials (or put in .env at repo root)
export OMADA_API_URL="https://use1-omada-northbound.tplinkcloud.com"
export OMADA_ID="<omadacId>"
export OMADA_CLIENT_ID="<client_id>"
export OMADA_CLIENT_SECRET="<client_secret>"

# Inspect device list
python scripts/omada_api_inspect.py sites/{siteId}/devices

# Inspect switch traffic stats (the actual response shape)
python scripts/omada_api_inspect.py sites/{siteId}/statistics/devices \
    --param device_mac=AA-BB-CC-DD-EE-FF \
    --param device_type=switch \
    --param interval=hourly

# Pass an already-valid token to skip the auth step
export OMADA_ACCESS_TOKEN="<token>"
python scripts/omada_api_inspect.py sites/{siteId}/devices
```

The script handles pagination automatically and pretty-prints the full JSON response.

### Pre-Commit Checks
This project uses **pre-commit** hooks (`.pre-commit-config.yaml`) that run automatically on every `git commit`. A commit is **blocked** if any hook fails. The hooks run in this order:

1. **Ruff** — linting (with auto-fix) and formatting
2. **Pre-commit-hooks** — trailing whitespace, end-of-file, YAML/JSON/TOML validation, merge conflicts, large files, line endings
3. **Pylint** — additional code quality checks (on `custom_components/` only)
4. **Mypy** — static type checking (on `custom_components/` only)
5. **Pytest + Coverage Gate** — runs the full test suite with coverage measurement:
   - If any test **fails**, the commit is blocked.
   - If code coverage **drops** below the baseline stored in `.coverage-threshold`, the commit is blocked.
   - If coverage **increases**, the baseline is automatically bumped and staged into the commit.
   - The coverage gate script lives at `scripts/check_coverage.sh`.

**CRITICAL — Test Coverage Requirement:**
- **Every code change MUST be accompanied by tests** that cover the new or modified code.
- Never commit code that would reduce the overall coverage percentage.
- Before committing, always run `pytest tests/ --cov=custom_components.omada_open_api --cov-report=term-missing` to verify coverage is maintained or improved.
- If adding new modules or features, write tests **before** the implementation — see TDD Workflow below.
- The current coverage baseline is tracked in `.coverage-threshold` — this file is updated automatically by the pre-commit hook and should not be edited manually.

## TDD Workflow (Red/Green/Refactor)

All agentic development in this project MUST follow the red/green/refactor cycle. **Never write implementation code before writing tests.**

### The Three Stages

**RED — Write failing tests first:**
1. Write test(s) that describe the expected behavior of the unit/feature you are about to implement.
2. Run `pytest tests/<file> -x -v --tb=short` and **confirm the tests FAIL**.
3. Verify the failure is for the *right* reason (e.g., `ImportError`, `AttributeError`, `AssertionError`) — not a syntax error or unrelated crash.
4. If tests pass immediately without any implementation, the test is wrong — fix it until it fails correctly.
5. **Do NOT commit during RED.** The pre-commit hook blocks failing commits by design. This is correct behavior — RED is a local verification step only.

**GREEN — Write minimum implementation:**
1. Write the smallest amount of implementation code that makes the failing tests pass.
2. Do not add features, handle edge cases, or refactor at this stage. Only make the tests go green.
3. Run `pytest tests/<file> -x -v --tb=short` and confirm **all tests pass**.
4. If tests still fail, fix the implementation — do not modify the tests to force them to pass.

**REFACTOR — Clean up:**
1. Improve code quality: naming, structure, duplication, type hints, docstrings.
2. Do not change observable behavior.
3. After every refactor change, re-run `pytest tests/<file> -x -v --tb=short`. Tests must stay green.
4. Once satisfied, run the full suite and coverage check:
   ```bash
   pytest tests/ --cov=custom_components.omada_open_api --cov-report=term-missing
   ```
5. Commit — message must include `(TDD)` suffix:
   ```bash
   git commit -m "feat: add X (TDD)"
   ```

### Commit Convention for TDD
- Commits completing a TDD cycle MUST end with `(TDD)` in the message, e.g.:
  - `feat: add gateway WAN sensor (TDD)`
  - `fix: handle token expiry edge case (TDD)`
  - `refactor: extract pagination helper (TDD)`
- This makes TDD cycles traceable in the git log.

### One TDD Cycle = One Unit
- Apply TDD one unit at a time (one function, one method, one entity class, one coordinator method).
- Complete the full RED→GREEN→REFACTOR cycle before starting the next unit.
- This maps directly to the incremental test development rule below (1-3 tests per cycle).

## Testing Strategy & Best Practices

### Test Organization
Organize tests by functionality into separate files:
- `test_config_flow.py`: Config flow, user input validation, error handling
- `test_api.py`: API client functionality, token management, authentication
- `test_coordinator.py`: Data update coordinator, polling, error recovery
- `test_<platform>.py`: Platform-specific tests (sensors, switches, etc.)

### Incremental Test Development
**CRITICAL**: Each increment is one TDD cycle. Add tests **before** implementation, not alongside or after:
1. **Write 1-3 tests** describing the next unit's behavior (RED stage)
2. **Run pytest immediately** to confirm tests FAIL for the right reason
3. **Implement** the minimum code to make them pass (GREEN stage)
4. **Refactor** then rerun to confirm still green
5. **Commit** with `(TDD)` suffix before moving to the next unit
6. **Never batch large test additions** — file corruption risk increases significantly and defeats TDD discipline

Example workflow:
```bash
# RED: write tests, confirm failure
pytest tests/test_config_flow.py -x -v --tb=short  # should FAIL
# GREEN: implement, confirm pass
pytest tests/test_config_flow.py -x -v --tb=short  # should PASS
# Commit
git commit -m "feat: add error handling for config flow (TDD)"
# Repeat for next unit
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

## Quality Scale Enforcement

### quality_scale.yaml Contract
The file `custom_components/omada_open_api/quality_scale.yaml` is the **single source of truth** for the integration's quality tier compliance.

**Rules for AI agents:**

1. **Never downgrade a rule** from `done` to `todo` or remove it without explicit user instruction and a documented reason.

2. **When modifying code**, verify affected rules still hold:
   - Removing `PARALLEL_UPDATES` from a platform file → violates `parallel-updates`
   - Adding `hass.data[DOMAIN]` → violates `runtime-data`
   - Storing `self._hass` in api.py → violates `inject-websession`
   - Removing `HomeAssistantError` wrapping → violates `action-exceptions`
   - Removing `py.typed` → violates `strict-typing`
   - Hardcoding entity names instead of `translation_key` → violates `entity-translations`
   - Hardcoding `_attr_icon` instead of using `icons.json` → violates `icon-translations`
   - Raising raw exceptions in service handlers → violates `exception-translations`

3. **When adding new entities**, ensure:
   - `translation_key` is set (not `_attr_name`)
   - Entry added to `strings.json` AND `translations/en.json` (keep in sync)
   - Entry added to `icons.json`
   - `entity_category` is set (DIAGNOSTIC or CONFIG) unless it's a primary entity
   - `device_class` is set if a standard class applies
   - `PARALLEL_UPDATES` exists in the platform file
   - `_attr_has_entity_name = True` (inherited from base or set explicitly)

4. **When adding new platforms**, ensure:
   - `PARALLEL_UPDATES` constant is defined
   - Platform is added to `PLATFORMS` list in `const.py`
   - Platform is added to `async_setup_entry` / `async_unload_entry`

5. **When modifying config flow**, ensure:
   - `async_step_reauth` still exists (`reauthentication-flow`)
   - `async_step_reconfigure` still exists (`reconfiguration-flow`)
   - `async_set_unique_id` + `_abort_if_unique_id_configured` still present (`unique-config-entry`)
   - Credentials are validated before entry creation (`test-before-configure`)

6. **When modifying translations**, always run:
   ```bash
   cp custom_components/omada_open_api/strings.json \
      custom_components/omada_open_api/translations/en.json
   ```

7. **Before finalizing any change**, mentally verify:
   - Would the quality_scale.yaml rules still all hold?
   - Is test coverage still ≥ 95%?
   - Does mypy strict still pass?

### Quality Rules Quick Reference
| Rule | What to preserve |
|------|-----------------|
| `parallel-updates` | `PARALLEL_UPDATES` constant in every platform file |
| `has-entity-name` | `_attr_has_entity_name = True` on all entities |
| `runtime-data` | Typed `entry.runtime_data`, never `hass.data[DOMAIN]` |
| `strict-typing` | `py.typed` marker + full type hints |
| `icon-translations` | All icons in `icons.json`, not `_attr_icon` |
| `entity-translations` | All names via `translation_key` in `strings.json` |
| `exception-translations` | `exceptions` section in `strings.json` |
| `action-exceptions` | `HomeAssistantError` wrapping in service handlers |
| `inject-websession` | No `self._hass` / `self.hass` in api.py |
| `diagnostics` | `diagnostics.py` exists |
| `reauthentication-flow` | `async_step_reauth` in config_flow.py |
| `reconfiguration-flow` | `async_step_reconfigure` in config_flow.py |
| `dynamic-devices` | Coordinator listeners for new device discovery |

## CI/CD Pipeline

### Continuous Integration (`.github/workflows/ci.yml`)
Runs on every push to `main` and every pull request targeting `main`. Mirrors the pre-commit hooks exactly:

| CI Job | Pre-commit Equivalent | What it checks |
|--------|----------------------|----------------|
| **Lint & Format** | `ruff --fix` + `ruff-format` | Ruff lint + format (same `pyproject.toml` rules) |
| **Lint & Format** | `pylint` | Pylint on `custom_components/` |
| **Type Check** | `mypy` | Mypy strict on `custom_components/omada_open_api/` |
| **Test & Coverage** | `scripts/check_coverage.sh` | Pytest + `--cov-fail-under` from `.coverage-threshold` |
| **HACS & hassfest** | *(CI only)* | HACS repo validation + HA hassfest manifest check |

### Release Pipeline (`.github/workflows/release.yml`)
Tag-based release triggered by pushing a version tag (`v*`).

The pipeline has 3 sequential jobs:
1. **Quality Gate** — full lint, format, typecheck, test+coverage, HACS & hassfest (same checks as CI)
2. **Version Consistency** — verifies the git tag version matches `manifest.json` version
3. **Create GitHub Release** — builds `omada_open_api.zip`, reads `RELEASE_NOTES.md` for release body (falls back to git log if missing), publishes GitHub Release

### How to Create a Release

#### Prerequisites
Before creating a release, ensure:
- All feature/fix code is committed and pushed to `main`
- All tests pass locally: `pytest tests/ -v`
- Coverage meets the threshold in `.coverage-threshold`: `pytest tests/ --cov=custom_components.omada_open_api --cov-report=term-missing`
- Linting passes: `ruff check custom_components/ tests/`
- Type checking passes: `mypy --config-file pyproject.toml custom_components/omada_open_api/`
- The latest CI run on `main` is green (check GitHub Actions)

#### Step-by-Step Release Process

**Step 1 — Determine the new version number:**

Use semantic versioning (`MAJOR.MINOR.PATCH`):
- `PATCH` (e.g., 1.3.1 → 1.3.2): Bug fixes, minor improvements, CI fixes
- `MINOR` (e.g., 1.3.2 → 1.4.0): New features, new entity types, new platforms
- `MAJOR` (e.g., 1.4.0 → 2.0.0): Breaking changes (config flow changes requiring re-setup, removed entities, renamed config keys)

Check the current version:
```bash
python3 -c "import json; print(json.load(open('custom_components/omada_open_api/manifest.json'))['version'])"
```

**Step 2 — Update version in BOTH files:**

The version MUST be updated in exactly two files. Both must contain the same version string:
- `custom_components/omada_open_api/manifest.json` → `"version": "X.Y.Z"`
- `pyproject.toml` → `version = "X.Y.Z"`

Example for version 1.4.0:
```bash
# In manifest.json: change "version": "1.3.1" to "version": "1.4.0"
# In pyproject.toml: change version = "1.3.1" to version = "1.4.0"
```

**Step 3 — Write release notes (`RELEASE_NOTES.md`):**

The release pipeline reads `RELEASE_NOTES.md` from the repo root for polished, user-facing release notes. This file MUST be written by the AI agent before committing.

1. Run `git log --oneline` between the previous tag and HEAD to see all changes:
   ```bash
   PREV_TAG=$(git tag --sort=-v:refname | head -1)
   git log "${PREV_TAG}..HEAD" --oneline --no-merges
   ```
2. Analyze the commits and write `RELEASE_NOTES.md` in the repo root using this format:
   ```markdown
   ## What's New in vX.Y.Z

   ### Features
   - Concise, user-facing description of new feature

   ### Improvements
   - Concise description of improvement or enhancement

   ### Bug Fixes
   - Concise description of what was fixed

   ### Breaking Changes
   - Description of breaking change and any migration steps required
   ```
   **Rules:**
   - Only include sections that have entries (omit empty sections entirely).
   - Write user-facing descriptions, NOT raw commit messages. Summarize and group related commits.
   - Keep each bullet to one or two sentences.
   - Use the actual version number in the heading (e.g., `## What's New in v1.5.0`).
   - Do NOT include an installation footer — the pipeline appends one automatically.

**Step 4 — Commit the version bump and release notes:**
```bash
git add custom_components/omada_open_api/manifest.json pyproject.toml RELEASE_NOTES.md
git commit -m "release: bump version to 1.4.0"
```
The pre-commit hooks will run. The commit must pass all hooks.

**Step 5 — Tag and push in a single command:**
```bash
git tag v1.4.0
git push origin main --tags
```
This pushes the commit AND the tag together, which triggers both CI (for the push) and Release (for the tag).

**Step 6 — Monitor the pipelines:**
- Go to `https://github.com/bullitt186/ha-omada-open-api/actions`
- **CI pipeline** should pass (triggered by the push to main)
- **Release pipeline** should pass (triggered by the v* tag)
- Release pipeline runs: Quality Gate → Version Consistency → Create GitHub Release
- On success, a GitHub Release is created with `omada_open_api.zip` attached and the `RELEASE_NOTES.md` content as the release body

**Step 7 — Verify the release:**
- Check `https://github.com/bullitt186/ha-omada-open-api/releases` for the new release
- Verify the release notes read well and the attached zip file is correct

#### Handling Pipeline Failures After Tagging

If the release pipeline fails after you've pushed the tag:

1. **Fix the issue** in a new commit on `main`
2. **Delete the old tag** locally and remotely:
   ```bash
   git tag -d v1.4.0
   git push origin :refs/tags/v1.4.0
   ```
3. **Recreate the tag** on the fix commit and push:
   ```bash
   git tag v1.4.0
   git push origin main --tags
   ```
4. This triggers a new Release pipeline run with the updated code

**Note:** Only do this if the GitHub Release was NOT successfully created. If it was, delete the release from the GitHub UI first, then retag.

#### Quick Reference Commands
```bash
# Check current version
python3 -c "import json; print(json.load(open('custom_components/omada_open_api/manifest.json'))['version'])"

# Run all local quality checks before release
ruff check custom_components/ tests/ && \
ruff format --check custom_components/ tests/ && \
pylint --rcfile=pyproject.toml custom_components/omada_open_api/ && \
mypy --config-file pyproject.toml custom_components/omada_open_api/ && \
pytest tests/ --cov=custom_components.omada_open_api --cov-fail-under=$(cat .coverage-threshold) -v

# Full release sequence (after version files and RELEASE_NOTES.md are written)
git add custom_components/omada_open_api/manifest.json pyproject.toml RELEASE_NOTES.md
git commit -m "release: bump version to X.Y.Z"
git tag vX.Y.Z
git push origin main --tags

# Fix-and-retag sequence (if release pipeline fails)
git tag -d vX.Y.Z
git push origin :refs/tags/vX.Y.Z
# ... fix and commit ...
git tag vX.Y.Z
git push origin main --tags
```

**CRITICAL — Version Consistency:**
- `manifest.json` `version` and `pyproject.toml` `version` MUST always match each other and the git tag.
- The release workflow has a `version-check` job that blocks the release if tag ≠ manifest version.
- When asked to prepare a release, always update both version files before tagging.
- Never push a tag without first committing the matching version bump.
