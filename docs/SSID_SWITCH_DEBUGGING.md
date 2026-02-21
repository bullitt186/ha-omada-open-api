# SSID Switch Debugging Guide

## Problem: SSID Switches Not Appearing

If you have write/admin access to your Omada controller but SSID switches are not appearing in Home Assistant, follow this debugging guide.

## Step 1: Enable DEBUG Logging

Add to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.omada_open_api: debug
```

Restart Home Assistant, then reload the Omada integration.

## Step 2: Check Home Assistant Logs

Look for these key log messages during integration reload:

### Expected Log Messages

**During Coordinator Initialization:**
```
INFO Initialized coordinator for site 'MySite' with X devices and Y SSIDs
DEBUG SSIDs for site 'MySite': ['WiFi-Main', 'WiFi-Guest', ...]
```

**During Write Access Check:**
```
INFO Write access check result: GRANTED (checked site: site_xxx)
INFO Total SSIDs across 1 site(s): Y
```

**During SSID Switch Creation:**
```
DEBUG SSID switch setup: has_write_access=True, coordinator_count=1
DEBUG Processing site 'site_xxx': found Y SSIDs: ['WiFi-Main', 'WiFi-Guest', ...]
INFO Created Y SSID switches from Y total SSIDs across 1 site(s)
```

### Problem Indicators

**No SSIDs Found:**
```
INFO Initialized coordinator for site 'MySite' with X devices and 0 SSIDs
INFO No SSIDs returned for site MySite — site may have no configured wireless networks
```
**Possible causes:**
- Site genuinely has no WiFi networks configured
- API endpoint failed (check for WARNING messages)
- Pagination issue with large SSID counts

**Write Access Denied:**
```
INFO Write access check result: DENIED (checked site: site_xxx)
INFO Skipping SSID switches — API credentials have viewer-only access
```
**Solution:** Verify your API credentials have "Read/Write" permissions in Omada Controller settings.

**Invalid SSID Data:**
```
WARNING Invalid SSID data for site site_xxx: missing required fields (id/wlanId): {...}
WARNING Site site_xxx: filtered out N invalid SSIDs, M valid remaining
```
**Possible cause:** API returned unexpected data format. Please report this with full logs.

**Missing Site Device:**
```
ERROR Site device 'site_xxx' not found in runtime_data for SSID switches
```
**Possible cause:** Initialization order issue. Please report this bug.

## Step 3: Run Diagnostic Service

In Home Assistant:
1. Go to **Developer Tools** → **Services**
2. Select service: `omada_open_api.debug_ssid_switches`
3. Click **Call Service**
4. Check Home Assistant logs for detailed diagnostic output

The service will log:
- Write access status
- Number of coordinators and site devices
- Per-site SSID breakdown with IDs, names, and broadcast status
- Count of created SSID switch entities

## Step 4: Manual API Verification

If logs show 0 SSIDs but you know they exist, manually verify the API:

1. Find your integration's API credentials in `.storage/core.config_entries`
2. Make a test API call:

```bash
curl -H "Authorization: AccessToken YOUR_TOKEN" \
  "https://YOUR_REGION-omada-northbound.tplinkcloud.com/openapi/v1/YOUR_OMADA_ID/sites/YOUR_SITE_ID/wireless-network/ssids?page=1&pageSize=100"
```

Expected response should include an array of SSID objects with `id`, `wlanId`, `name`, and `broadcast` fields.

## Common Issues and Solutions

### Issue: Write Access Check Returns False Despite Admin Credentials

**Symptoms:**
```
INFO Write access check result: DENIED
```

**Debug Steps:**
1. Verify API credentials in Omada Controller:
   - Go to Settings → Open API
   - Ensure your API application has "Read/Write" permission (not "Read-Only")
   - Re-generate credentials if needed
2. Re-configure the integration with new credentials
3. Reload integration and check logs

### Issue: SSIDs Exist But Switches Not Created

**Symptoms:**
```
INFO Initialized coordinator with X devices and Y SSIDs
INFO Created 0 SSID switches from Y total SSIDs
WARNING Write access is enabled and Y SSIDs were found, but no SSID switches were created
```

**Debug Steps:**
1. Check for validation errors in logs (invalid SSID data)
2. Run diagnostic service to see SSID structure
3. Look for missing required fields: `id`, `wlanId`, `name`
4. Report issue with full diagnostic output

### Issue: Coordinator Shows 0 SSIDs But Controller Has Networks

**Symptoms:**
```
INFO Initialized coordinator with X devices and 0 SSIDs
WARNING Failed to fetch SSIDs for site MySite: ... (error_code: ...)
```

**Debug Steps:**
1. Check error code in logs (e.g., -44114 = token expired, -1007 = no permission)
2. Verify site ID is correct
3. Test manual API call (see Step 4)
4. Check if DPI (Deep Packet Inspection) is enabled on gateway
5. Verify API endpoint accessibility

### Issue: Only Some SSIDs Create Switches

**Symptoms:**
```
WARNING Site site_xxx: filtered out N invalid SSIDs, M valid remaining
```

**Debug Steps:**
1. Check which SSIDs are invalid in logs
2. Look for SSIDs missing `id` or `wlanId` fields
3. This may indicate API version mismatch or partial data
4. Report with full SSID data structure from diagnostic service

## Reporting Issues

If you still have problems after following this guide, please report an issue with:

1. Full Home Assistant logs (with DEBUG level) from integration reload
2. Output from the diagnostic service
3. Screenshot of your Omada Controller API settings (hide sensitive data)
4. Omada Controller version
5. Number of sites and SSIDs configured

## Advanced: Force SSID Switch Creation

If you need to temporarily disable SSID switches even with write access (e.g., to avoid accidental network disruption), there is currently no config option. This feature may be added in a future release.

To permanently disable, remove write permissions from the API credentials and reload the integration.
