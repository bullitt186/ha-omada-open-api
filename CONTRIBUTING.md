# Contributing to TP-Link Omada Open API

Contributions are welcome — bug reports, feature requests, pull requests, documentation, and testing with different Omada setups.

Coding agents and people follow the same rules: read [AGENTS.md](AGENTS.md) before you start. The maintainer reviews every pull request against the [Definition of Done](#definition-of-done) below.

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
3. Make changes and add tests; add an entry under `[Unreleased]` in [CHANGELOG.md](CHANGELOG.md)
4. Ensure all checks pass: `make check` (`ruff`, `pylint`, `mypy`, `pytest` with coverage)
5. Open a pull request and fill in the pull request template

<!-- repo-kit:begin v1 (managed, do not edit; https://github.com/bullitt186/repo-kit) -->
## Definition of Done

This section is shared by all repositories of this maintainer
([repo-kit](https://github.com/bullitt186/repo-kit)). The maintainer reviews
every pull request, from people and from coding agents, against exactly this
list. `AGENTS.md` explains how to get there.

A pull request is done when:

1. **Scope** – it solves one issue or topic; unrelated changes are left out.
2. **Design** – the design is written down (issue, pull request or commit
   message); an ADR in `docs/adr/` is added or updated where `AGENTS.md` asks for
   one, and no *Accepted* ADR is contradicted.
3. **Tests** – behaviour changes and bug fixes have tests that fail without the
   change; expected values come from a specification or real data.
4. **Docs** – README, `docs/`, examples and `CHANGELOG.md` (`[Unreleased]`)
   describe the new state; upgrade notes exist for breaking changes.
5. **Checks** – the repository's full local check and all CI checks, including
   `PR hygiene`, are green on the current default branch.
6. **Hygiene** – no secrets, personal data or generated artefacts; commit
   messages follow Conventional Commits (`feat:`, `fix:`, `docs:`, …).
7. **Template** – the pull request template is filled in truthfully.

### What needs the maintainer

These are decided by the maintainer and may take longer: breaking changes,
claims about hardware or external systems that need evidence from a real device,
new runtime dependencies, and anything that changes releases or repository
settings. Say so in the pull request; it saves a review round.

### Labels

| Label | Meaning |
|---|---|
| `needs-info` | waiting for information from the reporter |
| `needs-hardware` | needs a test on a device or system the maintainer does not have |
| `blocked` | waits for another issue or pull request (linked) |
| `decision` | needs a maintainer decision |
| `breaking` | changes behaviour users rely on |
| `adr` | adds or changes an architecture decision record |
| `no-test-change`, `skip-changelog` | maintainer waiver for a PR hygiene rule |
<!-- repo-kit:end -->
