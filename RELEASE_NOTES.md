## What's Changed in v1.12.1b1

> **Beta release:** HACS offers this version only when beta versions are
> enabled for this repository. Please report problems before the stable
> release.

This release fixes large installations losing sites, devices or clients,
makes four entity options take effect, and fixes two Fusion gateway setup
problems. Large parts of the setup code and the configuration flow were
restructured internally; please report anything that behaves differently
from v1.12.0.

### Fixed

- **Sites and devices beyond the first 100** (#186). Controllers with more
  than 100 sites, and sites with more than 100 devices, now show all of them
  instead of only the first 100.
- **Clients beyond the first 1,000** (#194). On a site with more than 1,000
  clients, selected clients past the first 1,000 lost their entities. All
  client pages are now read.
- **Four entity options had no effect** (#184). *Client count sensors*,
  *Radio utilization sensors*, *Network access switch* and *Reconnect button*
  were saved but ignored. They are now honored. All four default to on, so
  nothing changes unless you turned one off. If you did, its entities are no
  longer updated and show as unavailable; remove them from the entity
  settings if you do not want them listed.
- **Adding an already configured Fusion gateway** (#195) showed an "Unknown
  error" instead of telling you that the gateway is already configured.
- **Fusion gateway after a site ID change** (#196). When a Fusion gateway
  reports its only site under a new ID, for example after a firmware update,
  the integration kept requesting the old site. It now uses the current site,
  and your existing entities, their history and automations stay as they
  are.

### Changed

- The configuration flow now uses the same API client as the integration
  itself, and the setup code is split into smaller modules. There is no
  change in behavior intended; this makes later fixes easier.
