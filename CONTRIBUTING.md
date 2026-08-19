# Contributing to TP-Link Omada Open API

Contributions are welcome — bug reports, feature requests, pull requests, documentation, and testing with different Omada setups.

## Reporting Bugs & Requesting Features

Use our [issue templates](https://github.com/bullitt186/ha-omada-open-api/issues/new/choose): [Bug Report](https://github.com/bullitt186/ha-omada-open-api/issues/new?template=bug_report.yml) (the form walks you through what's needed — debug logs, diagnostics, environment) or [Feature Request](https://github.com/bullitt186/ha-omada-open-api/issues/new?template=feature_request.yml) (describe the problem, not just the fix). For general questions, use the [Community forum](https://community.home-assistant.io/) instead.

Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md) first — your issue may already be covered there.

## Development

This project uses VS Code devcontainers for a consistent development environment.

### Prerequisites

- Docker ([Desktop](https://docs.docker.com/desktop/) or [Engine](https://docs.docker.com/engine/install/))
- [Visual Studio Code](https://code.visualstudio.com/) with the [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) extension

### Getting Started

```bash
git clone https://github.com/bullitt186/ha-omada-open-api.git
cd ha-omada-open-api
# Open in VS Code → Reopen in Container
# Dev HA instance at http://localhost:8123
```

### Code Quality

Pre-commit hooks enforce **Ruff** (lint + format), **Pylint**, **Mypy**, and **pytest with a coverage gate** on every commit.

```bash
ruff check custom_components/ && ruff format --check custom_components/
mypy custom_components/omada_open_api/
pytest tests/ -v
pytest tests/ --cov=custom_components.omada_open_api --cov-report=html
```

## Submitting a Pull Request

1. Fork the repository
2. Create a feature branch
3. Make changes and add tests
4. Ensure all checks pass (`pytest`, `ruff`, `mypy`, `pylint`)
5. Open a pull request
