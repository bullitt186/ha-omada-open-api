## What's Changed in v1.11.1b1

> **Beta release.** This is a pre-release for testing before v1.11.1. HACS
> offers it only if you enabled beta versions for this integration (see
> "Beta Versions" in the README). Please report results and problems in a
> GitHub issue and mention the beta version.

This patch release fixes VPN monitoring on controllers that require a VPN
type filter, and stops repeated VPN errors in the log on controllers that
don't support the VPN stats endpoints.

### Fixed

- **All VPN types are reported on controllers that need a type filter** (#63,
  #67, PR #93). Some controllers, such as Software Controller 6.3 and Fusion
  gateways, only answer the VPN stats endpoints when a VPN type is given.
  The integration used to ask for WireGuard only. It now queries every type
  each endpoint accepts, so IPsec site-to-site tunnels and L2TP, PPTP and
  OpenVPN servers and clients appear as well. Existing WireGuard entities
  are unchanged.
- **No more VPN errors every minute on unsupported controllers** (#63,
  PR #91, PR #93). If a controller rejects every request for a VPN type, as
  reported on Software Controller 6.2.14.11, the integration logs one
  warning and checks again every hour instead of logging errors on every
  poll. When the controller starts answering, the entities return and an
  info message is logged.

**Full Changelog**: https://github.com/bullitt186/ha-omada-open-api/compare/v1.11.0...v1.11.1b1
