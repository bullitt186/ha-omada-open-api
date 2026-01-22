# Home Assistant Omada Open API Integration

Home Assistant integration for TP-Link Omada SDN using the Open API.

## Development Setup

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

2. Open the project in VS Code:
   ```bash
   code .
   ```

3. When prompted, click "Reopen in Container" (or use Command Palette: `Dev Containers: Reopen in Container`)

4. Wait for the container to build and install dependencies

5. The Home Assistant development instance will be available at http://localhost:9123

### Development Commands

Inside the devcontainer:

#### Code Quality (Automated in VSCode)
- **Format code**: `ruff format custom_components/` (auto on save)
- **Lint code**: `ruff check custom_components/` (auto on save)
- **Type check**: `mypy custom_components/omada_open_api/`
- **Run pylint**: `pylint custom_components/omada_open_api/`
- **Run all checks**: `pre-commit run --all-files`

#### Testing
- **Run tests**: `pytest tests/ -v`
- **Run with coverage**: `pytest tests/ --cov=custom_components.omada_open_api --cov-report=html`

#### Running Home Assistant
- **Start HA**: `hass -c config` or use VSCode task "Run Home Assistant"
- **Access**: http://localhost:8123

See [CODING_STANDARDS.md](CODING_STANDARDS.md) for detailed coding guidelines.

## Code Quality Standards

This project follows **Home Assistant's official coding standards**:

- ✅ **Ruff** - Primary linter and formatter (88 char lines)
- ✅ **Pylint** - Additional code quality checks
- ✅ **Mypy** - Strict type checking enabled
- ✅ **Pre-commit hooks** - Auto-checks before each commit
- ✅ **Full type hints** - All functions must be typed
- ✅ **PEP 8 & PEP 257** - Style and docstring compliance

**VSCode is configured to automatically:**
- Format code on save using Ruff
- Organize imports on save
- Show inline type hints
- Display linting errors in real-time

**All code is automatically checked before commit** via pre-commit hooks.

## Features

This integration provides:

- Controllers, Sites, Access Points, Switches, and Gateways as devices
- Sensors for device status, client counts, and network statistics
- Device trackers for connected clients
- Binary sensors for online/offline status

## API Documentation

- [Omada Open API Documentation](https://use1-omada-northbound.tplinkcloud.com/doc.html#/home)

## License

MIT
