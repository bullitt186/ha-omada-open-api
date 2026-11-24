# ADR-0002: Shared polling through DataUpdateCoordinator classes

- **Status:** Accepted
- **Date:** 2026-11-24

## Context

The integration reads controller, device, client, gateway and application data
from an Omada controller or Fusion gateway and exposes it as many Home
Assistant entities. This ADR is recorded after the fact: it states the
architecture as `AGENTS.md` described it before ADRs existed.

## Decision

The integration follows Home Assistant's coordinator architecture. Controller
I/O is asynchronous. Shared polling lives in `DataUpdateCoordinator` classes;
entities consume coordinator data and do not poll on their own. API and
authentication behaviour stays in the API and auth modules, which are passed
into coordinators and entities. List endpoints are paginated with their
documented `page`/`pageSize` parameters, using `totalRows` to fetch all
results. An option that disables an optional feature prevents both its
entities and its coordinator from being created.

## Consequences

One request per data set and interval serves all entities that use it. New
data comes in through a coordinator, not through an entity. A failing
non-critical endpoint must not discard unrelated coordinator data.
