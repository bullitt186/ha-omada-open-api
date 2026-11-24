# Changelog

All notable changes are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions: [SemVer](https://semver.org/).

## [Unreleased]

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
