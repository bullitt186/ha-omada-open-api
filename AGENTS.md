# Repository Instructions

## Scope and sources of truth

This repository is a Home Assistant `hub` integration for TP-Link Omada Open
API controllers and Fusion gateways. It exposes controller, infrastructure
device, client, gateway, and application data through Home Assistant entities.

Use the repository configuration as the source of truth:

- `pyproject.toml` defines Python 3.14, Ruff, Pylint, mypy, pytest, and coverage
  configuration.
- `.pre-commit-config.yaml` and `.github/workflows/ci.yml` define the enforced
  quality gate.
- `custom_components/omada_open_api/quality_scale.yaml` defines the integration
  quality-scale contract. Do not downgrade a `done` rule without explicit user
  direction and a documented reason.
- `custom_components/omada_open_api/manifest.json`, `hacs.json`, and the
  workflow files define distribution and release behavior.
- For Home Assistant implementation details, consult a local
  `ha-developer-docs/` directory when it is available; otherwise use the
  official Home Assistant developer documentation. Use the official Omada
  documentation for API questions. Treat live controller payloads as
  authoritative when they disagree with documentation.

Do not change application code, dependencies, build/CI configuration, MCP/tool
configuration, or secrets unless the requested work requires it.

When dependency work is required, declare runtime dependencies in
`custom_components/omada_open_api/manifest.json` and development/test tooling
in `requirements_dev.txt`; keep the declared Python compatibility aligned with
`pyproject.toml` and CI.

## Repository layout

- `custom_components/omada_open_api/` — integration source, manifest,
  translations, diagnostics, and quality-scale contract.
- `tests/` — pytest suite for API, coordinators, config flow, and entity
  platforms.
- `scripts/check_coverage.sh` — pre-commit coverage gate.
- `scripts/deploy.sh` — deploys only to the local devcontainer Home Assistant.
- `.devcontainer/` — VS Code and Docker Compose development environments.
- `.github/workflows/` — CI and tag-triggered release workflows.
- `README.md`, `TROUBLESHOOTING.md`, and `CONTRIBUTING.md` — user and
  contributor documentation.

The integration follows Home Assistant's coordinator architecture:

- Keep controller I/O asynchronous.
- Put shared polling in `DataUpdateCoordinator` classes; entities consume
  coordinator data rather than polling independently.
- Keep API/authentication behavior in the existing API/auth modules and pass
  dependencies into coordinators and entities.
- Paginate list endpoints with their documented `page`/`pageSize` parameters
  and use `totalRows` to fetch all results.

## Development environment

Worktrees must be created below `.worktrees/<name>` inside the repository. The
devcontainer only bind-mounts the repository root, so sibling worktrees are not
usable there.

The host-side `.venv` can point to a container-only Python. When working from
the host, run Python tooling and commits in the devcontainer, for example:

```bash
docker compose -f .devcontainer/docker-compose.yml exec devcontainer bash
```

Then run commands from the relevant repository/worktree directory. If Git in a
container cannot resolve a worktree because its `.git` file contains a host
path, create the required container-side gitdir symlink and add that worktree to
Git's `safe.directory` list when Git reports an ownership warning.

Two development environments exist and do not share state:

- VS Code Dev Containers uses `devcontainer.json` and does not provide a local
  Home Assistant instance.
- `make devcontainer` starts the Compose devcontainer plus Home Assistant at
  `http://localhost:8123`.

`make deploy` is local-only: it refuses non-local targets, copies the
integration into `/config`, and restarts Home Assistant. A config-entry reload
does not re-import Python modules; use a full Home Assistant restart after code
changes.

## Coding and Home Assistant rules

- Target Python 3.14. Keep code fully typed and compatible with strict mypy.
- Follow Ruff formatting (88-character line length) and import ordering.
- Use async I/O only; do not block the event loop. Prefer `asyncio.timeout`.
- Use `raise ... from err` for wrapped exceptions and handle non-critical API
  failures without discarding unrelated coordinator data.
- Use Google-style docstrings where a docstring is needed. Write comments as
  complete sentences ending with a period.
- Use `%s` logging placeholders. Do not log credentials, tokens, cookies, CSRF
  values, or passwords.
- Use constants from `homeassistant.const` where applicable; integration
  constants belong in `const.py` and use upper-case names.
- Keep config-entry data and user preferences separated as the existing code
  does. Use typed `entry.runtime_data`, not `hass.data[DOMAIN]`.

Preserve the quality-scale guarantees when touching affected code:

- New entities need stable unique IDs, entity naming via `translation_key`, and
  matching entries in both `strings.json` and `translations/en.json`. Add
  matching icon translations in `icons.json`.
- Set an entity category for diagnostic/config entities and a standard device
  class where one applies. Keep `PARALLEL_UPDATES` in each entity platform.
- New platforms must be added to `PLATFORMS` and set up/unloaded with the config
  entry.
- Preserve reauthentication, reconfiguration, unique-config-entry, credential
  validation, diagnostics, and dynamic-discovery behavior.
- A removed dynamic resource should make its existing entity unavailable; do
  not fabricate a replacement state or remove a potentially customized registry
  entry.
- An option that disables an optional feature must prevent both its entities and
  its optional API polling/coordinator from being created.

For user-visible config-flow or entity changes, keep translations synchronized:

```bash
cp custom_components/omada_open_api/strings.json \
  custom_components/omada_open_api/translations/en.json
```

## Controller and security constraints

The integration supports OAuth client credentials and Fusion web sessions.
Preserve existing authentication behavior, including token refresh and Fusion's
unsafe IP cookie jar, CSRF header, JSON-without-content-type handling, and
single-site fallback.

Fusion web logins invalidate existing sessions. Reuse one session during a
browser/API test sequence. After direct Fusion testing, restart local Home
Assistant before validating its entities, and do not perform another Fusion
login during that final runtime check.

Never write credentials, tokens, cookies, CSRF values, or development secrets
to source files, test fixtures, logs, shell/browser output, commits, or pull
request text.

VPN client, server, and site-to-site payloads have different connection and
traffic semantics. Test each type against its own schema; do not reuse
server/S2S peer-count semantics for a VPN client when the controller exposes
client-level telemetry.

## Test-driven changes and verification

For every change under `custom_components/` or `tests/`, use this sequence for
one unit at a time:

1. Add one to three focused tests first and run them to confirm the expected
   failure (RED).
2. Add the smallest implementation that makes them pass (GREEN).
3. Refactor without changing behavior and rerun the focused tests.
4. Before committing, run the relevant full verification. Commits that complete
   this cycle end with `(TDD)`.

Do not commit during RED and do not bypass failing pre-commit hooks. Mock
external APIs through the Home Assistant-facing interfaces; cover successful,
error, and availability behavior relevant to the change.

Use the narrowest relevant check while iterating:

```bash
make test
pytest tests/test_<area>.py -x -v --tb=short
```

Before handing off a source or test change, run the full local gate:

```bash
make check
```

This runs Ruff lint/format checks, Pylint, strict mypy, and the parallel pytest
suite with coverage. Do not edit `.coverage-threshold` manually; the
pre-commit coverage script updates it only when coverage increases.

Do not commit generated or local-runtime artifacts covered by `.gitignore`,
including `.venv/`, `htmlcov/`, `.coverage*`, `.pytest_cache/`, `.mypy_cache/`,
`.ruff_cache/`, `config/`, `.worktrees/`, `.env`, or `ha-developer-docs/`.

Verification has three independent layers when applicable: focused/unit tests,
local Home Assistant runtime verification (registered entities, state, and
logs), and the hosted CI run. Do not treat one layer as proof of another.

## Documentation and release requirements

Update user-facing documentation when changing configuration, entities,
services/actions, supported behavior, or troubleshooting guidance. Keep public
documentation in `README.md` and `TROUBLESHOOTING.md` accurate.

For a release, first ensure the feature/fix work is on `main`, local checks and
CI are green, and then:

1. Select a semantic version: patch for fixes, minor for new features/entities,
   major for breaking changes.
2. Update the same version in `custom_components/omada_open_api/manifest.json`
   and `pyproject.toml`.
3. Write user-facing `RELEASE_NOTES.md` for that exact version.
4. Commit the release metadata, tag `vX.Y.Z`, and push `main` plus the tag.

The release workflow validates that the tag matches `manifest.json`, runs the
quality gate, builds the integration archive, and creates the GitHub release.

## Definition of done

- The requested behavior is implemented within the existing architecture.
- Tests were added/updated before implementation where source behavior changed.
- Relevant unit tests and `make check` pass.
- Required translations, diagnostics, documentation, and quality-scale rules
  are preserved.
- Local Home Assistant behavior and hosted CI are verified when the change
  affects runtime integration behavior.
- `git diff --check` is clean, and no secrets or generated runtime artifacts
  are included in the change.
