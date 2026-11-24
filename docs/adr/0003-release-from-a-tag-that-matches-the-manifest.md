# ADR-0003: Release from a tag that matches the manifest

- **Status:** Accepted
- **Date:** 2026-11-24

## Context

The integration is distributed through HACS, which installs GitHub releases.
This ADR is recorded after the fact: it states the release process as
`AGENTS.md` described it before ADRs existed.

## Decision

A release is a `vX.Y.Z` tag on a merge commit of `main`, with the same version
in `custom_components/omada_open_api/manifest.json` and `pyproject.toml`. The
tag-triggered release workflow checks that the tag matches `manifest.json`,
runs the quality gate, builds the integration archive and creates the GitHub
release with the pre-written `RELEASE_NOTES.md`. Beta versions use a PEP 440
pre-release suffix (`X.Y.ZbN`, `aN`, `rcN`), may be tagged on an integration
branch and are published as GitHub pre-releases, never as latest. Release tags
`v*` cannot be deleted or moved.

## Consequences

The version is bumped and the release notes are written in a pull request
before tagging. A tag on the wrong commit can only be corrected by the
maintainer. HACS offers betas only to users who enabled beta versions.
