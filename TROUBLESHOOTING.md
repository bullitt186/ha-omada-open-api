# Troubleshooting

## Integration Not Loading

1. Check Home Assistant logs at **Settings → System → Logs**
2. Verify `custom_components/omada_open_api/manifest.json` exists
3. Restart Home Assistant after installation

## Authentication Errors

1. Double-check Client ID, Client Secret, and Omada ID — no extra spaces
2. Verify region (cloud) or API URL (local) is correct
3. Ensure outbound HTTPS is not blocked by a firewall
4. Use **Settings → Devices & Services → TP-Link Omada Open API → Reauthenticate** to re-enter credentials

> **"Controller ID not exist" (error -7131)?** Re-copying the Omada ID won't help — the free Omada Cloud/Central Essentials tier has no Open API at all (see [README → Features](README.md#features)). Upgrade to Standard, or switch to **Local** with a self-hosted controller.

## No Entities Created

1. Verify you selected at least one site during setup
2. Check that devices and clients exist in your Omada Controller
3. Check logs for coordinator update errors

## Missing Application Traffic Sensors

1. Enable **DPI** on your gateway: Omada Controller → Gateway → Settings → DPI
2. Verify applications were selected during setup (or add them via Options → Application selection)
3. Application data resets daily at midnight

## Missing VPN or WAN Speed-Test Entities

1. In **Settings → Devices & Services → TP-Link Omada Open API → Configure → Gateway Entity Settings**, confirm the relevant feature is enabled.
2. VPN entities are created only for configured tunnels. The primary tunnel entity is a connectivity binary sensor named after the tunnel; peer/client telemetry is diagnostic and disabled by default.
3. WAN speed-test entities require a gateway WAN port that exposes the speed-test endpoint. Use the **Run speed test** button and watch the **Speed test running** binary sensor while Omada performs the test.
4. After adding or removing a VPN tunnel in Omada, wait for the next device polling interval or reload the integration.

## Entities Showing "Unavailable"

1. Confirm the device is online in the Omada Controller
2. Check logs for API errors
3. Try increasing the polling interval via Options if you hit rate limits

Transient API failures raise `UpdateFailed`, which triggers Home Assistant's automatic back-off and retry — a brief "Unavailable" during a controller hiccup is expected and should self-resolve.

## Token Errors

Token refresh is fully automatic: OAuth2 tokens refresh 5 minutes before expiry, and an expired refresh token triggers full re-authentication via client credentials. If you see persistent token errors in logs, authentication itself has failed (raising `ConfigEntryAuthFailed`) — use the **Reauthenticate** flow to obtain fresh credentials.

## Reconfiguring the Integration

To change the controller type, API URL, credentials, or selected sites without deleting and re-adding the integration, use **Settings → Devices & Services → TP-Link Omada Open API → ⋮ → Reconfigure**. The reconfigure flow walks through the same steps as initial setup and preserves your options (clients, applications, intervals).

## Repair Notifications

The integration may create repair notifications under **Settings → Repairs**:

- **Read-only API credentials** — Your API application has viewer-only permissions. Device controls (PoE, LED, reboot) are unavailable. Update the application permissions in your Omada controller.
- **No gateway for DPI tracking** — You selected applications for traffic tracking but no gateway was found. DPI requires an Omada gateway in your network.

## Diagnostics

**Settings → Devices & Services → TP-Link Omada Open API → ⋮ → Download diagnostics** produces a JSON file with config data, coordinator summaries (device/client counts, tracked apps), write-access status, and site device info. Tokens, secrets, MAC addresses, and IPs are redacted automatically.

## Debug Services

### `omada_open_api.debug_ssid_switches`

Dumps SSID switch entity diagnostics for a config entry to the HA log — useful when entities aren't created as expected.

```yaml
service: omada_open_api.debug_ssid_switches
data:
  config_entry_id: "your_config_entry_id_here"  # from the entity registry
```
