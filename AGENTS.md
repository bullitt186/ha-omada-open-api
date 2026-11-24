# AGENTS.md

<!-- repo-kit:begin v2 (managed, do not edit; https://github.com/bullitt186/repo-kit) -->
## How to work in this repository (all coding agents)

This block is shared by all repositories of this maintainer and kept in sync by
[repo-kit](https://github.com/bullitt186/repo-kit). Repository-specific
instructions follow below it. They add detail; where they contradict this block,
this block wins, unless an ADR in `docs/adr/` records the exception.

A pull request that follows this block passes review without rework. The
maintainer reviews against the same rules: the **Definition of Done** in
`CONTRIBUTING.md`.

### Build the right thing

1. Read this file to the end, `CONTRIBUTING.md`, `docs/SCOPE.md` and the
   architecture decision records in `docs/adr/` (start with `docs/adr/README.md`).
   An *Accepted* ADR and the scope are binding. If your change needs a different
   decision, write a new ADR that supersedes the old one, in the same pull request.
2. Work from an issue. A feature or behaviour change needs an issue the maintainer
   has labelled `accepted`; if there is none, open one, describe the problem (not
   only the solution) and wait. Only a **small fix** may skip the issue: it repairs
   documented behaviour, changes fewer than about 50 lines of code, and adds no
   dependency, interface, setting or file format.
3. Build what the issue asks for and nothing else. Ideas you have on the way become
   a new issue, not part of this pull request. No reformatting, renaming or
   refactoring that the change does not need.
4. Prefer the smallest complete change: reuse what the repository already has
   (helpers, patterns, dependencies) before adding anything; no new dependency for
   a few lines. Fix the root cause, not the symptom.
5. Never guess protocol values, API fields or hardware behaviour. Take them from a
   source and name it; mark anything unconfirmed as an assumption.

### Design first

Write the design down before the code: the behaviour that changes, the modules
and interfaces involved, and how it is tested. Put it in the issue or the pull
request description; for a small change the commit message is enough.

Write an ADR (`docs/adr/`, see its README) when the change:

- adds, removes or replaces a runtime dependency or external service,
- changes a public interface: API, CLI, configuration keys, file or data formats,
  entity or topic names, anything users or other systems rely on,
- changes the architecture: module boundaries, data flow, persistence, threading,
- sets a security, privacy or compatibility rule,
- reverses or replaces an earlier ADR, or changes `docs/SCOPE.md`.

Bug fixes and refactorings inside existing decisions need no ADR.

### Tests

Design the test cases from the specification, then implement the change together
with them. A one-test-at-a-time red/green cycle is not required.

- A bug fix starts with a regression test that reproduces the bug. Run it and
  confirm it fails **for the reason the bug describes**, not because of a build,
  import or signature error. Then fix the bug and commit the test with the fix.
- Expected values come from the specification: documentation, a protocol table,
  a manual, the issue, or a recorded real payload. Never from running the code
  under test and copying its output; such a test only proves the code does what
  it does.
- Assert observable results (output, state, sent request, raised error), not only
  that something was called.
- Tests are fast, deterministic and offline. A flaky test is a bug to fix, not to
  re-run.
- Changing an expected value in an existing test needs a reason in the commit
  message that names the source of the new value.
- Coverage shows what ran, not whether a test notices a wrong result. Run mutation
  testing on the code you changed (see Commands below); kill a surviving mutant
  with a test, or say in the pull request why it is equivalent.
- Do not weaken lint rules, thresholds or checks to make a change pass; fix the
  code. A justified exception gets a comment next to it and a note in the commit
  message. Thresholds are only ever raised.

### Documentation

Documentation changes in the same pull request as the behaviour it describes:
README, `docs/`, configuration examples, the ADRs and `CHANGELOG.md`. Outdated
documentation counts as a bug. Relative links in Markdown must point to files
that exist.

Changelog entries go under `[Unreleased]`, in the Keep a Changelog sections
(Added, Changed, Fixed, Removed, Security). Write them for the user of the
project: what changes for them and what they have to do, not which functions
moved. A breaking change gets an entry under "Upgrade notes" with the steps.
Name outside contributors and link their issue or pull request. Releases, tags
and version numbers are the maintainer's
([release standard](https://github.com/bullitt186/repo-kit/blob/main/docs/RELEASING.md)).

### Commits and branches

- One branch per topic from the current default branch; never commit to the
  default branch. Agents working in parallel use their own git worktree; never
  run checkout, switch, reset, stash or clean in a checkout someone else uses.
- Commit each completed step with a Conventional Commits message (`feat:`,
  `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, `ci:`); the body says why.
  Code, comments, commit messages and pull requests are in English.
- Reference the issue: `Closes #N` on GitHub; `Refs #N` on Forgejo, which closes
  an issue as soon as a commit with `Closes` is pushed.
- Never commit or push on red; never use `--no-verify` or skip hooks; treat every
  hook finding as work to do.

### Before you open the pull request

- Run the repository's **fast check** before every commit and the **full check**
  when your change can affect what it covers (see Commands below). Both must pass.
- Merge or rebase onto the current default branch and run the checks again.
- Fill in the pull request template completely; tick only what you did and say
  why anything stays unticked.
- After pushing, watch CI yourself. A red check on your pull request is your work,
  also when it looks unrelated.
- No secrets, tokens, personal data, local paths, host names or IP addresses in
  code, tests, fixtures, logs, commits or pull request text.

### Continuous integration

CI follows the repo-kit [CI standard](https://github.com/bullitt186/repo-kit/blob/main/docs/CI_STANDARD.md):
tests, lint and format, type check, build, secret scan, dependency review, static
analysis and `PR hygiene`. PR hygiene fails when code changes come without a test
change or a `CHANGELOG.md` entry, when `docs/SCOPE.md` changes without an ADR,
when an ADR is malformed or missing from the index, when a changed Markdown file
has a broken relative link, when code from an outside contributor links no issue,
or when a pull request changes more than about 800 lines of code and tests. Only
the maintainer can waive a rule (labels `no-test-change`, `skip-changelog`,
`large-change`). Do not ask for a waiver when a test, entry or split is possible.

### Respect

Do not change CI configuration, branch protection, release workflows, licence,
`docs/SCOPE.md` or this block unless the issue asks for it. Maintainer decisions
recorded in issues and ADRs are not up for silent change.
<!-- repo-kit:end -->

## This repository

### Purpose

Scope and non-goals: [docs/SCOPE.md](docs/SCOPE.md)

This repository is a Home Assistant `hub` integration for TP-Link Omada Open
API controllers and Fusion gateways. It exposes controller, infrastructure
device, client, gateway, and application data through Home Assistant entities.
It is distributed through HACS.

### Commands

| Task | Command |
|---|---|
| Install / set up | `make install` (creates `.venv` from `requirements_dev.txt`, installs the pre-commit hook), or open the devcontainer (see "Development environment") |
| Fast check (before every commit, also the stop hook) | `ruff check custom_components/ tests/ && ruff format --check custom_components/ tests/ && mypy --config-file pyproject.toml custom_components/omada_open_api/ && pytest tests/ -x -q --tb=short -n auto` (what `scripts/agent-stop-check.sh` runs) |
| Full check (before every pull request) | `make check` (Ruff, Pylint, strict mypy, pytest with coverage; mirrors CI) |
| Mutation testing of changed code | `make mutate` (mutmut on the integration modules changed against `origin/main`; `make mutate-results` lists survivors) |
| Tests only | `make test` (stops at the first failure) or `pytest tests/test_<area>.py -x -v --tb=short` |

CI additionally runs the HACS and hassfest validation, a secret scan, CodeQL
and dependency review, and repo-kit's `PR hygiene`.

### Scope and sources of truth

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

### Layout

- `custom_components/omada_open_api/` — integration source, manifest,
  translations, diagnostics, and quality-scale contract.
- `tests/` — pytest suite for API, coordinators, config flow, and entity
  platforms.
- `scripts/check_coverage.sh` — pre-commit coverage gate (total baseline).
- `scripts/check_module_coverage.sh` — per-module minimum (95%, Platinum
  `test-coverage`); run by the pre-commit gate and CI.
- `scripts/mutate.sh` — mutation testing with mutmut (`make mutate`).
- `scripts/agent-stop-check.sh` — fast check for the Claude Code `Stop` hook.
- `scripts/deploy.sh` — deploys only to the local devcontainer Home Assistant.
- `.devcontainer/` — VS Code and Docker Compose development environments.
- `.github/workflows/` — CI, security, weekly mutation testing, and
  tag-triggered release workflows.
- `README.md`, `TROUBLESHOOTING.md`, and `CONTRIBUTING.md` — user and
  contributor documentation.
- `docs/SCOPE.md` — purpose, scope and non-goals.
- `docs/adr/` — architecture decision records (index in `docs/adr/README.md`).
- `CHANGELOG.md` — running change log (`[Unreleased]`); `RELEASE_NOTES.md` —
  notes of the release being prepared.

The integration follows Home Assistant's coordinator architecture:

- Keep controller I/O asynchronous.
- Put shared polling in `DataUpdateCoordinator` classes; entities consume
  coordinator data rather than polling independently.
- Keep API/authentication behavior in the existing API/auth modules and pass
  dependencies into coordinators and entities.
- Paginate list endpoints with their documented `page`/`pageSize` parameters
  and use `totalRows` to fetch all results.

### Development environment

Worktrees must be created below `.worktrees/<name>` inside the repository. The
devcontainer only bind-mounts the repository root, so sibling worktrees are not
usable there ([ADR-0004](docs/adr/0004-repository-exceptions-to-the-shared-workflow.md)).

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

### CodeGraph

This repository uses CodeGraph. The index lives in `.codegraph/` (ignored by
Git); if it is missing, run `codegraph init .` once. Before using `rg`, `find`, or
opening multiple files to understand cross-file behavior, use the
`codegraph_explore` MCP tool when it is available. It returns relevant symbols,
their current source, and call paths.

The CLI fallback is:

```bash
codegraph explore "<question or symbol names>" --path .
```

Use `codegraph node <symbol> --path .` for one symbol and its callers/callees.
After changing code, run `codegraph sync .` before relying on graph
relationships in a later investigation. CodeGraph complements rather than
replaces direct source reads, tests, or static analysis.

### Browser verification

When a change affects the Home Assistant UI, config flow, entity registration,
or another browser-visible runtime behavior, verify it in the local Home
Assistant instance with `playwright-cli` when a runtime check is applicable.
Start with `playwright-cli open http://localhost:8123`, use `snapshot` and its
element references for interactions, and close the Playwright-managed browser
when finished. This browser is separate from the user's live browser; do not
attach to or alter the user's session unless they explicitly ask.

Treat browser verification as a separate layer from unit tests and `make
check`. Do not put credentials, tokens, cookies, CSRF values, or screenshots
containing them in source, logs, or commits. Follow the Fusion session and
post-login runtime-check constraints above when browser testing a Fusion
gateway.

### Coding and Home Assistant rules

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

### Controller and security constraints

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

### Design and test specifics

The shared block's design-first and test rules apply. In this repository:

- The design names the affected modules and the Omada API endpoints and fields
  involved.
- The specification for expected values is the issue or requirement, documented
  Home Assistant behavior, and the Omada API documentation (or a recorded live
  payload where it disagrees with the documentation). Cover successful, error,
  and availability behavior relevant to the change.
- Behavioral assertions are entity state, attributes, availability, the request
  sent to the controller, or the raised error. Mock external APIs through the
  Home Assistant-facing interfaces.

Line coverage shows which code ran, not whether a test notices a wrong result.
Check test strength with mutation testing (mutmut):

```bash
make mutate
make mutate-all
make mutate-results
```

`make mutate` mutates only the integration modules changed against
`origin/main`, including uncommitted changes; `make mutate-all` mutates the
whole integration (more than 13,000 mutants) and takes hours. Treat a
surviving mutant in code you changed as a missing or weak assertion: add a
test that kills it, or state in the pull request why the mutant is equivalent
to the original. The scheduled `Mutation testing` workflow runs the full
mutation run weekly and reports the score; it does not block pull requests.

Keep the lint, complexity, type-checking, and coverage thresholds in
`pyproject.toml`, `.pre-commit-config.yaml`, and the coverage scripts as they
are. When a change exceeds a threshold, refactor. Raise a threshold or add a
suppression only as a justified exception, with the reason in a comment next to
it and in the commit message.

Run the repository's pre-commit hook as part of every commit (`make install`
installs it).

In Claude Code, `scripts/agent-stop-check.sh` runs as a `Stop` hook: when the
working tree has changes, it runs Ruff, strict mypy, and the unit tests, and
sends the agent back to work if one of them fails. The hook is registered in
the tracked `.claude/settings.json`; keep machine-specific settings and secrets
in the untracked `.claude/settings.local.json`.

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

### Documentation and release requirements

Update user-facing documentation when changing configuration, entities,
services/actions, supported behavior, or troubleshooting guidance. Keep public
documentation in `README.md` and `TROUBLESHOOTING.md` accurate.

Every pull request that changes code or user-visible behavior adds an entry
under `[Unreleased]` in `CHANGELOG.md` (PR hygiene checks it). `CHANGELOG.md`
is the running record; `RELEASE_NOTES.md` holds only the user-facing notes of
the release being prepared, which the release workflow publishes.

Releases follow the repo-kit [release standard](https://github.com/bullitt186/repo-kit/blob/main/docs/RELEASING.md);
versions and tags are the maintainer's. `RELEASE_NOTES.md` uses the release-notes
structure of that standard. For a release, first ensure the feature/fix work is
merged to `main` through a pull request, local checks and CI are green, and then:

1. Select a semantic version: patch for fixes, minor for new features/entities,
   major for breaking changes.
2. Update the same version in `custom_components/omada_open_api/manifest.json`
   and `pyproject.toml`.
3. Move the `[Unreleased]` entries of `CHANGELOG.md` to a section for the
   new version, and write user-facing `RELEASE_NOTES.md` for that exact
   version from them.
4. Commit the release metadata on a branch and land it on `main` through a
   pull request (see "Branch and tag protection").
5. Stop for the maintainer's acceptance; nothing is tagged before it.
6. After the merge and the acceptance, fetch `main` and tag the merge commit explicitly, never a
   local `main` that may be stale:

   ```bash
   git fetch origin main
   git show <merge-sha>:custom_components/omada_open_api/manifest.json
   git tag -a vX.Y.Z <merge-sha> -m "vX.Y.Z"
   git push origin vX.Y.Z
   ```

   Confirm that the manifest shows `X.Y.Z` before tagging. After the push,
   confirm that the release workflow succeeded and that the GitHub release is
   marked as latest.

The release workflow validates that the tag matches `manifest.json`, runs the
quality gate, builds the integration archive, and creates the GitHub release.

#### Beta releases

Pre-releases let opted-in HACS users test a release before it goes public:

1. Use a PEP 440 pre-release version such as `X.Y.Zb1` (or `aN`/`rcN`) in
   `manifest.json` and `pyproject.toml`, and start `RELEASE_NOTES.md` with a
   beta notice.
2. A beta may be tagged on an integration branch (`vX.Y.Zb1`) once local checks
   pass and CI is green on a pull request from that branch.
3. The release workflow publishes such tags as GitHub pre-releases and never
   marks them as latest. HACS offers them only to users who enabled beta
   versions for this repository.
4. Increment the suffix for each further beta. For the final release, merge to
   `main`, drop the suffix and the beta notice, and tag `vX.Y.Z` on `main`.

The workflow rejects any other version format, and it rejects a stable tag that
is not on `main`.

#### Branch and tag protection

GitHub rulesets protect the default branch and release tags. Treat them as
hard constraints:

- `main` accepts changes only through pull requests. Never push directly to
  `main`, force-push it, or delete it.
- A pull request can merge only when these required checks pass on its current
  head, with the branch up to date with `main`: `Lint & Format`,
  `Type Check (mypy strict)`, `Test & Coverage`, `HACS & hassfest`,
  `Secret scan`, and `hygiene / PR hygiene`. This repository runs its own
  `.github/workflows/security.yml` (secret scan, CodeQL, dependency review)
  instead of the repo-kit one; keep it. If a check is renamed in a workflow, update the ruleset in the
  same change, otherwise pull requests wait on a check that never reports.
- No approving review is required, but a red required check is never bypassed.
- Single-purpose pull requests are squash-merged. An integration branch that
  bundles other pull requests must use a merge commit, so GitHub marks the
  bundled pull requests as merged
  ([ADR-0004](docs/adr/0004-repository-exceptions-to-the-shared-workflow.md)).
  Linear history is not required.
- Release tags `v*` cannot be deleted, moved, or force-pushed. A tag that
  points at the wrong commit cannot be fixed by an agent; stop and ask the
  maintainer, who can correct it with the admin bypass.
- Never use, request, or work around the admin bypass, and never change or
  disable the rulesets, unless the maintainer explicitly asks for that specific
  change.

When giving the maintainer shell commands to run, do not put `#` comments on
the command lines. The maintainer's zsh does not treat them as comments, so
they are passed to the command as arguments.

### Definition of Done additions

The shared Definition of Done is in `CONTRIBUTING.md`. In this repository a
change is also done only when:

- The requested behavior is implemented within the existing architecture.
- Required translations, diagnostics, documentation, and quality-scale rules
  are preserved.
- Local Home Assistant behavior and hosted CI are verified when the change
  affects runtime integration behavior.
- `git diff --check` is clean.

### CI standard exceptions

- Static analysis runs as CodeQL advanced setup in the repository's own
  `security.yml`, not as GitHub default setup.
- Workflows of outside contributors from forks need approval only for first-time
  contributors who are new to GitHub, not for every outside contributor
  ([ADR-0004](docs/adr/0004-repository-exceptions-to-the-shared-workflow.md)).
