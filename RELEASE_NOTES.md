## What's Changed in v1.11.0b1

> **Beta release.** This is a pre-release for testing before v1.11.0. HACS
> offers it only if you enabled beta versions for this integration (see
> "Beta Versions" in the README). Please report results and problems in a
> GitHub issue and mention the beta version.

This release fixes the token-refresh regression from v1.10.1 that forced a
manual reauthentication roughly every two hours. It also fixes several
controller-compatibility issues and adds the radio band to client trackers.

### Fixed

- **Token refresh works again; no more reauthentication loop** (#63, #66,
  #65, PR #70). v1.10.1 sent the `refresh_token` grant as a JSON body, which
  Omada controllers reject with `-1001 Invalid request parameters`. The
  request now uses a form-encoded body, so credentials still stay out of the
  URL. If a controller ever rejects a refresh with `-1001` again, the
  integration falls back to a fresh client-credentials login instead of
  requiring a manual reauthentication.
- **VPN status sensors on controller 6.3** (#67, PR #71). A bare HTTP 400 from
  the VPN stats endpoints now triggers the same `vpnType` filter fallback as
  the `-1001` error code.
- **WAN speed test on non-Fusion controllers** (#68, PR #72). The Fusion-only
  ISP dashboard endpoint no longer fails the whole speed-test update when the
  controller answers with HTTP 404 or `-1600 Unsupported request path`. The
  regular speed-test results stay available.
- **Device hierarchy ready for Home Assistant 2027.8** (#69, PR #73). Devices
  now link to their parent by device registry ID (`via_device_id`) instead of
  the deprecated `via_device` identifier. This also fixes a link to an
  identifier that was never registered.
- **"Client bandwidth sensors" option is honored** (#65, PR #74). Turning it
  off now prevents the client downloaded/uploaded and RX/TX activity sensors
  from being created.
- **AP RX/TX activity no longer alternates with 0** (#85). Some controllers,
  such as the OC200, refresh AP traffic counters only about every 150 seconds.
  When a poll sees unchanged counters, the last rate is now kept instead of
  publishing 0.0 and then twice the real rate on the next poll. An AP reports
  0 only after its counters have been flat for three polls, and for at least
  5 minutes.
- **Client and application selections can be cleared** (#65). Removing every
  tracked client or application in the options dialog previously restored the
  old selection on save.

### Added

- **Radio band and channel on client trackers** (#78). Wireless client
  `device_tracker` entities now expose `band` (`2.4 GHz`, `5 GHz` or `6 GHz`)
  and `channel` attributes.

### Documentation

- Explains which settings reduce API load with many tracked clients:
  application traffic makes one request per tracked client per cycle.

### Maintenance

- Development tooling updated: ruff 0.16.3, pylint 4.0.7, pytest-cov,
  pytest-timeout. Also updated: the GitHub Actions for CodeQL, hassfest and
  release.

### Thanks

- @oralallen82 (PR #64) and @matanmesika (PR #77) for the token-refresh
  fixes and live-controller verification.
- @sebmuc99 for the precise root-cause reports #67, #68 and #69.
- @vishlamba for #65, #66 and #78, @simonbosschieter for #85, and everyone
  who confirmed and tested #63.

---

**Upgrade note:** if your entry is currently waiting for reauthentication
because of the v1.10.1 token issue, reauthenticate once after updating. Token
refresh then continues automatically.
