# ADR-0004: Repository exceptions to the shared workflow

- **Status:** Accepted
- **Date:** 2026-11-24

## Context

repo-kit's shared rules and its CI standard assume squash merges, worktrees under
`.claude/worktrees/`, the kit's `security.yml` with CodeQL default setup, and maintainer
approval for every outside contributor's fork workflow. This repository already worked
differently before repo-kit, recorded here after the fact from `AGENTS.md`, the workflows and
the repository settings:

- Integration branches bundle several pull requests (for example release and beta branches).
  GitHub marks the bundled pull requests as merged only when the integration branch lands with
  a merge commit (`AGENTS.md`, "Branch and tag protection", since 2026-10-11).
- The devcontainer bind-mounts only the repository root, so a worktree outside it cannot be
  used inside the container (`AGENTS.md`, "Development environment", since 2026-08-19).
- `.github/workflows/security.yml` predates the kit and runs secret scan, CodeQL (advanced
  setup) and dependency review; the `main` ruleset requires its `Secret scan` check with
  strict status checks.
- The fork workflow approval policy is set to first-time contributors who are new to GitHub.

## Decision

We keep these exceptions:

1. Single-purpose pull requests are squash-merged; an integration branch that bundles other pull
   requests lands with a merge commit.
2. Worktrees live under `.worktrees/<name>` inside the repository.
3. The repository keeps its own `security.yml`; it covers the CI standard's secret scan,
   dependency review and static analysis categories.
4. The repository keeps its fork workflow approval policy (first-time contributors new to
   GitHub). The reason is not recorded in the repository: Open, to be documented by the
   maintainer.

## Consequences

`kit.py check` reports `security.yml` as custom; that is expected. `kit.py github` keeps the
existing approval policy and the existing rulesets and only adds missing required checks.
Agents follow `AGENTS.md` for merges and worktrees in this repository. Changing any of these
needs a new ADR that supersedes this one.

## Alternatives considered

- Squash-merge integration branches: the bundled pull requests would show as closed, not merged.
- Worktrees under `.claude/worktrees/`: inside the repository root as well, but not where the
  existing tooling and `.gitignore` expect them; no gain for the change.
- Replace `security.yml` with the kit's version: would drop the CodeQL advanced setup and rename
  the required `Secret scan` check.
