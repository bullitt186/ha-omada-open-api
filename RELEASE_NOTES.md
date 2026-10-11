## What's Changed in v1.11.1

This patch release stops repeated VPN errors in the log on controllers that
don't support the VPN stats endpoints.

### Fixed

- **No more VPN stats errors every minute on unsupported controllers** (#63,
  PR #91). Some controllers, such as Omada Software Controller 6.2.14.11,
  reject the site-to-site, VPN server, and VPN client stats endpoints with
  HTTP 400, even after the WireGuard filter fallback. The integration now logs
  one warning per VPN type and stops polling that type until the entry is
  reloaded. Other errors are still retried on the next poll.

**Full Changelog**: https://github.com/bullitt186/ha-omada-open-api/compare/v1.11.0...v1.11.1
