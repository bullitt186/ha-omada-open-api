# Changelog

All notable changes are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions: [SemVer](https://semver.org/).

## [Unreleased]

### Fixed

- Home Assistant 2026.12 no longer logs device metadata deprecation warnings
  for Omada devices and tracked clients (#223, @hmmbob).

## [1.12.1] - 2026-11-25

### Fixed

- Controllers with more than 100 sites, and sites with more than 100 devices,
  now show all of them instead of only the first 100 (#186).
- On a site with more than 1,000 clients, selected clients past the first 1,000
  no longer lose their entities (#194).
- The options *Client count sensors*, *Radio utilization sensors*, *Network
  access switch* and *Reconnect button* now take effect; before, they were saved
  but ignored (#184).
- Adding an already configured Fusion gateway now says it is already configured
  instead of showing an "Unknown error" (#195).
- When a Fusion gateway reports its only site under a new ID, the integration
  now polls the current site and keeps the existing entities (#196).
- Mutation testing (`make mutate` and the weekly workflow) no longer fails for a
  module in which mutmut finds nothing to mutate, such as `services.py`, and no
  longer breaks on the tests of the developer scripts.

### Changed

- The configuration flow uses the integration's own API client, and the setup
  code is split into smaller modules; behaviour stays the same.

### Added

- Shared contributor and coding-agent setup from repo-kit: one `AGENTS.md`
  (shared block plus the existing repository rules), the Definition of Done in
  `CONTRIBUTING.md`, a pull request template, architecture decision records in
  `docs/adr/` (ADR-0001 to ADR-0004), `docs/SCOPE.md` with purpose, scope and
  non-goals, and the `PR hygiene` check (repo-kit v2). Feature requests are built
  after the maintainer labels the issue `accepted`; releases follow the repo-kit
  release standard. ADR-0004 records where this repository deliberately differs
  (merge commits for integration branches, `.worktrees/`, its own security workflow
  and fork approval policy).

### Security

- The developer script `scripts/omada_api_inspect.py` now validates TLS
  certificates. Pass `--insecure` to reach a local controller with a
  self-signed certificate (#209).
