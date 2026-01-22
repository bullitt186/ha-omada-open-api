# Code Quality & Style Guide

This project follows **Home Assistant's coding standards** to ensure high-quality, maintainable code.

## Overview

All code must comply with:
- **PEP 8**: Python code style guide
- **PEP 257**: Docstring conventions
- **Home Assistant Code Review Guidelines**
- **Full type hints** (Python 3.11+)

## Tools & Configuration

### Linting & Formatting

The project uses the following tools (automatically configured):

1. **Ruff** - Primary linter and formatter (replaces black, isort, flake8)
   - Line length: 88 characters
   - Auto-formats code on save in VSCode
   - Auto-organizes imports

2. **Pylint** - Additional code quality checks
   - Detects code smells and potential bugs
   - Enforces naming conventions

3. **Mypy** - Static type checking
   - Strict mode enabled
   - All functions must be fully typed

4. **Pytest** - Unit and integration testing
   - Async test support enabled
   - Coverage reporting available

### Pre-commit Hooks

Pre-commit hooks are configured to automatically check your code before each commit:

```bash
# Install hooks (already done in dev container)
pre-commit install

# Run manually on all files
pre-commit run --all-files
```

The hooks will:
- Format code with ruff
- Check and fix linting issues
- Verify type hints with mypy
- Run pylint checks
- Check YAML, JSON, TOML files
- Fix trailing whitespace and line endings

## Running Code Quality Checks

### Format Code
```bash
# Format all Python files
ruff format custom_components/

# Format specific file
ruff format custom_components/omada_open_api/sensor.py
```

### Lint Code
```bash
# Check all files
ruff check custom_components/

# Auto-fix issues
ruff check --fix custom_components/

# Check specific file
ruff check custom_components/omada_open_api/sensor.py
```

### Type Checking
```bash
# Check types
mypy custom_components/omada_open_api/

# Check specific file
mypy custom_components/omada_open_api/sensor.py
```

### Pylint
```bash
# Run pylint
pylint custom_components/omada_open_api/

# Check specific file
pylint custom_components/omada_open_api/sensor.py
```

### Run All Checks
```bash
# Using pre-commit
pre-commit run --all-files

# Using VSCode tasks
# Ctrl+Shift+P -> "Tasks: Run Task" -> "Lint with ruff"
# Ctrl+Shift+P -> "Tasks: Run Task" -> "Lint with pylint"
# Ctrl+Shift+P -> "Tasks: Run Task" -> "Type check with mypy"
```

## VSCode Integration

VSCode is configured to automatically:
- Format code on save using Ruff
- Organize imports on save
- Show type hints inline
- Display linting errors in real-time
- Run type checking in the background

### Keyboard Shortcuts
- `Shift + Alt + F` - Format document
- `Ctrl + Shift + P` -> "Organize Imports" - Sort imports

## Coding Style Guidelines

### String Formatting

**Use f-strings** for general string formatting:
```python
# Good
message = f"Device {device_name} is {status}"

# Bad
message = "{} is {}".format(device_name, status)
message = "%s is %s" % (device_name, status)
```

**Exception: Use % formatting for logging** (to avoid unnecessary formatting):
```python
# Good
_LOGGER.info("Can't connect to %s at %s", device_name, url)

# Bad (always formats even if logging is disabled)
_LOGGER.info(f"Can't connect to {device_name} at {url}")
```

### Type Hints

All functions must be fully typed:
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
    coordinator: OmadaDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    # ...
    return True
```

### Docstrings

Use Google-style docstrings:
```python
def calculate_bandwidth(self, tx_bytes: int, rx_bytes: int) -> float:
    """Calculate total bandwidth in Mbps.

    Args:
        tx_bytes: Transmitted bytes.
        rx_bytes: Received bytes.

    Returns:
        Total bandwidth in Mbps.

    Raises:
        ValueError: If bytes are negative.
    """
    if tx_bytes < 0 or rx_bytes < 0:
        raise ValueError("Bytes cannot be negative")
    return (tx_bytes + rx_bytes) * 8 / 1_000_000
```

### Imports

Use standard Home Assistant aliases:
```python
import voluptuous as vol
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
```

### Constants

- Use UPPER_CASE for constants
- Alphabetically order lists and dicts
- Prefer constants from `homeassistant.const`

```python
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
)

# Integration-specific constants
DOMAIN = "omada_open_api"
DEFAULT_SCAN_INTERVAL = 60
CONF_SITE_ID = "site_id"
```

### Error Handling

Always specify exception cause with `raise from`:
```python
try:
    result = await self.api.get_devices()
except OmadaApiError as err:
    raise UpdateFailed(f"Error fetching devices: {err}") from err
```

### Async/Await

- All I/O operations must be async
- Use `asyncio.timeout` (not deprecated `async_timeout`)
- Never block the event loop

```python
import asyncio

async def fetch_data(self) -> dict[str, Any]:
    """Fetch data with timeout."""
    try:
        async with asyncio.timeout(10):
            return await self.api.get_data()
    except TimeoutError as err:
        raise UpdateFailed("Timeout fetching data") from err
```

### Logging

- Use `_LOGGER` from `logging.getLogger(__name__)`
- No component name in messages (added automatically)
- No period at end of messages
- Never log sensitive data (tokens, passwords)

```python
import logging

_LOGGER = logging.getLogger(__name__)

# Good
_LOGGER.error("Failed to connect to controller at %s", self.host)
_LOGGER.debug("Received %d devices from API", len(devices))

# Bad
_LOGGER.error("omada_open_api: Failed to connect.")  # Don't add component name
_LOGGER.info(f"Using token: {self.token}")  # Never log tokens!
```

## Testing

### Running Tests
```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=custom_components.omada_open_api --cov-report=html

# Run specific test file
pytest tests/test_sensor.py -v

# Run specific test
pytest tests/test_sensor.py::test_sensor_state -v
```

### Test Structure
```python
async def test_sensor(hass: HomeAssistant) -> None:
    """Test the sensor."""
    # Setup
    entry = MockConfigEntry(domain=DOMAIN, data={...})
    entry.add_to_hass(hass)

    # Test
    assert await async_setup_entry(hass, entry, mock_add_entities)

    # Verify
    state = hass.states.get("sensor.omada_device_count")
    assert state.state == "10"
```

## Common Issues & Solutions

### Issue: "Line too long"
- **Solution**: Ruff will auto-format to 88 characters on save

### Issue: "Missing type hints"
- **Solution**: Add type hints to all function parameters and return values

### Issue: "Import not sorted"
- **Solution**: VSCode will auto-organize imports on save

### Issue: "F-string without placeholders"
- **Solution**: Remove f-prefix or add variables

### Issue: "Docstring missing"
- **Solution**: Add Google-style docstring to all public functions/classes

## Configuration Files

- **pyproject.toml** - All tool configurations (ruff, pylint, mypy, pytest)
- **.vscode/settings.json** - VSCode editor settings
- **.pre-commit-config.yaml** - Pre-commit hook configuration

## Resources

- [Home Assistant Developer Docs](https://developers.home-assistant.io/)
- [Code Review Checklist](https://developers.home-assistant.io/docs/creating_component_code_review)
- [Style Guidelines](https://developers.home-assistant.io/docs/development_guidelines)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [PEP 8 Style Guide](https://peps.python.org/pep-0008/)
