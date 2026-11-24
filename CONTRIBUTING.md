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

1. For a feature or behaviour change, open an issue first and wait until the
   maintainer labels it `accepted` (see "How ideas become changes" below)
2. Fork the repository and create a feature branch
3. Make changes and add tests; add an entry under `[Unreleased]` in [CHANGELOG.md](CHANGELOG.md)
4. Ensure all checks pass: `make check` (`ruff`, `pylint`, `mypy`, `pytest` with coverage)
5. Open a pull request and fill in the pull request template

<!-- repo-kit:begin v2 (managed, do not edit; https://github.com/bullitt186/repo-kit) -->
## Definition of Done

This section is shared by all repositories of this maintainer
([repo-kit](https://github.com/bullitt186/repo-kit)). The maintainer reviews
every pull request, from people and from coding agents, against exactly this
list. `AGENTS.md` explains how to get there.

A pull request is done when:

1. **Fit** – it fits `docs/SCOPE.md` and solves an issue labelled `accepted`
   (a small fix as defined in `AGENTS.md` needs no issue); a change of the scope
   comes with an ADR.
2. **Scope** – it does one thing; unrelated changes and unrequested extras are
   left out.
3. **Design** – the design is written down (issue, pull request or commit
   message); an ADR in `docs/adr/` is added or updated where `AGENTS.md` asks for
   one, and no *Accepted* ADR is contradicted.
4. **Tests** – behaviour changes and bug fixes have tests that fail without the
   change, for the right reason; expected values come from a specification or
   real data; surviving mutants in changed code are killed or explained.
5. **Docs** – README, `docs/`, examples and `CHANGELOG.md` (`[Unreleased]`,
   written for users) describe the new state; upgrade notes exist for breaking
   changes.
6. **Checks** – the fast and the full check pass locally, and all CI checks of the
   [CI standard](https://github.com/bullitt186/repo-kit/blob/main/docs/CI_STANDARD.md),
   including `PR hygiene`, are green on the current default branch.
7. **Hygiene** – no secrets, personal data or generated artefacts; Conventional
   Commits (`feat:`, `fix:`, `docs:`, …).
8. **Template** – the pull request template is filled in truthfully.

### How ideas become changes

1. Open an issue that describes the problem. The maintainer labels it `accepted`
   (fits the scope, a pull request is welcome), `out-of-scope` (with the reason),
   `needs-info` or `decision`.
2. Build only after `accepted`, following `AGENTS.md`. Link the issue with
   `Closes #N` (GitHub) or `Refs #N` (Forgejo).
3. To move the project in a new direction, propose a change of `docs/SCOPE.md`
   as an issue first; if accepted, it lands with an ADR.

### What needs the maintainer

Decided by the maintainer and possibly slower: breaking changes, claims about
hardware or external systems that need evidence from a real device, new runtime
dependencies, scope changes, large pull requests, and anything that changes
releases or repository settings. Say so in the pull request.

### Labels

| Label | Meaning |
|---|---|
| `accepted` | in scope; a pull request is welcome |
| `out-of-scope` | does not fit `docs/SCOPE.md` |
| `needs-info` | waiting for information from the reporter |
| `needs-hardware` | needs a test on a device or system the maintainer does not have |
| `blocked` | waits for another issue or pull request (linked) |
| `decision` | needs a maintainer decision |
| `breaking` | changes behaviour users rely on |
| `adr` | adds or changes an architecture decision record |
| `no-test-change`, `skip-changelog`, `large-change` | maintainer waiver for a PR hygiene rule |
<!-- repo-kit:end -->
