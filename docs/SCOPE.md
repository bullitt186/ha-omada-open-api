# Scope

What this project is for, so contributions go in the same direction. Changing this file is a
maintainer decision, recorded as an ADR.

## Purpose

A Home Assistant integration that connects to a TP-Link Omada SDN controller (cloud or local)
or a Fusion gateway through the Omada Open API, so Home Assistant users can monitor and control
their Omada infrastructure, clients and security data, and use them in automations. It is
distributed through HACS. See the [README](../README.md#about).

## In scope

- Controllers, access points, switches, gateways and clients reachable through the Omada Open
  API, and Fusion gateways through their local web session
  ([Supported Devices](../README.md#supported-devices)).
- Monitoring entities (sensors, binary sensors, device trackers, update entities) and control
  entities (switches, buttons, firmware install, client actions) where the credentials have the
  matching write permission ([Features](../README.md#features)).
- Data for other frontends, such as the threat heatmap sensors that the separate world heatmap
  card displays.

## Out of scope

- Lovelace cards and other frontend code: the integration is backend-only; the threat heatmap is
  visualised by the separate `ha-world-heatmap-card` repository.
- Omada Cloud Essentials (free tier): it has no Open API, so the integration cannot support it.
- Anything else: Open: to be decided by the maintainer.

## Direction

Feature requests are tracked as
[issues with the `enhancement` label](https://github.com/bullitt186/ha-omada-open-api/issues?q=is%3Aissue+is%3Aopen+label%3Aenhancement).
Beyond that: Open: to be decided by the maintainer.

## Principles

- Keep the Home Assistant quality-scale guarantees recorded in
  `custom_components/omada_open_api/quality_scale.yaml` (Platinum); a `done` rule is not
  downgraded without a documented reason.
- Shared polling through coordinators, asynchronous I/O only
  ([ADR-0002](adr/0002-shared-polling-through-data-update-coordinators.md)).
- Viewer-only credentials keep monitoring working; controls need the matching Open API write
  permission.
- Credentials, tokens, cookies and CSRF values are never logged or committed.
