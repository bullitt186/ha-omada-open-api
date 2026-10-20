## What's Changed in v1.11.1

This patch release fixes VPN monitoring on controllers that require a VPN
type filter, stops repeated VPN errors in the log on controllers that don't
support the VPN stats endpoints, lists every client in the client selection,
and retries setup when the controller is still starting.

### Fixed

- **Client selection lists every client and keeps your selection** (#96,
  PR #108). The setup and options flows only offered the first 200 clients
  the controller returned, and saving the options silently removed selected
  clients outside those 200. All known clients are now listed, online
  clients first. Selected clients the controller no longer lists stay
  selected and appear by MAC address, so you can still deselect them.
- **Setup retries when the controller is not reachable yet** (#97, PR #98).
  If Home Assistant starts before the Omada controller, a refused or failed
  connection no longer reports invalid credentials. Home Assistant retries
  the setup instead. Real credential and TLS certificate errors are still
  reported as before.
- **Uplink devices link to the right controller** (#94, PR #95). With more
  than one Omada config entry, parent devices are now looked up within the
  owning entry. This also replaces a device registry call that Home
  Assistant 2027.8 removes.
- **No more "Unclosed client session" errors with Fusion gateways**
  (PR #110). The integration and its setup and options dialogs now close
  their Fusion web sessions when they unload or finish, so reloading the
  integration no longer logs these errors.
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

**Full Changelog**: https://github.com/bullitt186/ha-omada-open-api/compare/v1.11.0...v1.11.1
