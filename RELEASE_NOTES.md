## What's Changed in v1.12.1

This release fixes large installations losing sites, devices or clients,
makes four entity options take effect, and fixes two Fusion gateway setup
problems. These fixes were tested as the beta v1.12.1b1, which ran without
problems.

### Fixes

- **Sites and devices beyond the first 100** (#186). Controllers with more
  than 100 sites, and sites with more than 100 devices, showed only the first
  100. All of them are now shown.
- **Clients beyond the first 1,000** (#194). On a site with more than 1,000
  clients, selected clients past the first 1,000 lost their entities. All
  client pages are now read.
- **Four entity options had no effect** (#184). *Client count sensors*,
  *Radio utilization sensors*, *Network access switch* and *Reconnect button*
  were saved but ignored. They now take effect.
- **Adding an already configured Fusion gateway** (#195) showed an "Unknown
  error". It now tells you that the gateway is already configured.
- **Fusion gateway after a site ID change** (#196). When a Fusion gateway
  reported its only site under a new ID, for example after a firmware update,
  the integration kept requesting the old site. It now uses the current site,
  and your existing entities, their history and automations stay as they are.

### Under the hood

- The configuration flow now uses the same API client as the integration, and
  the setup code is split into smaller modules. Behaviour stays the same.
- The project now follows a shared contributor setup: a changelog, a pull
  request template, architecture decision records and a scope document.

### Upgrade notes

None for most installations. All four options from #184 default to on. If you
turned one of them off earlier, its entities now stop updating and show as
unavailable; remove them in the entity settings if you do not want them
listed.

### Full changelog

[CHANGELOG.md](https://github.com/bullitt186/ha-omada-open-api/blob/v1.12.1/CHANGELOG.md)
· [Compare v1.12.0...v1.12.1](https://github.com/bullitt186/ha-omada-open-api/compare/v1.12.0...v1.12.1)
