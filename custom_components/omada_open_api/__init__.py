"""The Omada Open API integration."""

from __future__ import annotations

import datetime as dt
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .api import OmadaApiAuthError, OmadaApiClient
from .clients import normalize_client_mac
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_API_URL,
    CONF_APP_SCAN_INTERVAL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SCAN_INTERVAL,
    CONF_CLIENT_SECRET,
    CONF_DEVICE_SCAN_INTERVAL,
    CONF_OMADA_ID,
    CONF_REFRESH_TOKEN,
    CONF_SELECTED_APPLICATIONS,
    CONF_SELECTED_CLIENTS,
    CONF_SELECTED_SITES,
    CONF_TOKEN_EXPIRES,
    CONF_TOKEN_EXPIRES_AT,
    DEFAULT_APP_SCAN_INTERVAL,
    DEFAULT_CLIENT_SCAN_INTERVAL,
    DEFAULT_DEVICE_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import (
    OmadaAppTrafficCoordinator,
    OmadaClientCoordinator,
    OmadaSiteCoordinator,
)
from .devices import normalize_site_id

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Platforms to set up
PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DEVICE_TRACKER,
    Platform.SWITCH,
    Platform.UPDATE,
]


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the Omada Open API component.

    This integration only supports config flow setup.
    YAML configuration is not supported.
    """
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:  # pylint: disable=too-many-statements,too-many-branches
    """Set up Omada Open API from a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry for this integration

    Returns:
        True if setup was successful

    Raises:
        ConfigEntryAuthFailed: If authentication fails

    """
    _LOGGER.debug("Setting up Omada Open API integration")

    # Parse token expiration time
    token_expires_at = dt.datetime.fromisoformat(entry.data[CONF_TOKEN_EXPIRES_AT])

    # Create API client
    try:
        api_client = OmadaApiClient(
            hass,
            config_entry=entry,
            api_url=entry.data[CONF_API_URL],
            omada_id=entry.data[CONF_OMADA_ID],
            client_id=entry.data[CONF_CLIENT_ID],
            client_secret=entry.data[CONF_CLIENT_SECRET],
            access_token=entry.data[CONF_ACCESS_TOKEN],
            refresh_token=entry.data[CONF_REFRESH_TOKEN],
            token_expires_at=token_expires_at,
        )

        # Test connection and refresh token if needed
        sites = await api_client.get_sites()
        _LOGGER.info("Successfully connected to Omada API, found %d sites", len(sites))

    except OmadaApiAuthError as err:
        _LOGGER.exception("Authentication failed during setup")
        raise ConfigEntryAuthFailed(
            "Authentication failed. Please re-authenticate."
        ) from err

    # Create coordinators for each selected site
    coordinators: dict[str, OmadaSiteCoordinator] = {}
    selected_site_ids: list[str] = entry.data.get(CONF_SELECTED_SITES, [])

    # Get configured scan intervals
    device_interval = entry.data.get(
        CONF_DEVICE_SCAN_INTERVAL, DEFAULT_DEVICE_SCAN_INTERVAL
    )
    client_interval = entry.data.get(
        CONF_CLIENT_SCAN_INTERVAL, DEFAULT_CLIENT_SCAN_INTERVAL
    )
    app_interval = entry.data.get(CONF_APP_SCAN_INTERVAL, DEFAULT_APP_SCAN_INTERVAL)

    # Get all sites to find names for selected sites
    all_sites = await api_client.get_sites()
    sites_by_id = {site["siteId"]: site for site in all_sites}

    for site_id in selected_site_ids:
        site_info = sites_by_id.get(site_id)
        if not site_info:
            _LOGGER.warning("Selected site %s not found in available sites", site_id)
            continue

        site_name = site_info.get("name", site_id)

        coordinator = OmadaSiteCoordinator(
            hass=hass,
            api_client=api_client,
            site_id=site_id,
            site_name=site_name,
            scan_interval=device_interval,
        )

        # Perform initial data fetch
        await coordinator.async_config_entry_first_refresh()
        coordinators[site_id] = coordinator

        device_count = len(coordinator.data.get("devices", {}))
        ssid_count = len(coordinator.data.get("ssids", []))
        _LOGGER.info(
            "Initialized coordinator for site '%s' with %d devices and %d SSIDs",
            site_name,
            device_count,
            ssid_count,
        )
        if ssid_count > 0:
            ssid_names = [
                s.get("name", "Unknown") for s in coordinator.data.get("ssids", [])
            ]
            _LOGGER.debug(
                "SSIDs for site '%s': %s",
                site_name,
                ssid_names,
            )
        else:
            _LOGGER.debug(
                "No SSIDs found for site '%s' during initialization",
                site_name,
            )

    # Create client coordinators for selected clients
    client_coordinators: list[OmadaClientCoordinator] = []
    selected_client_macs: list[str] = entry.data.get(CONF_SELECTED_CLIENTS, [])

    if selected_client_macs:
        _LOGGER.info("Setting up tracking for %d clients", len(selected_client_macs))

        for site_id in selected_site_ids:
            site_info = sites_by_id.get(site_id)
            if not site_info:
                continue

            site_name = site_info.get("name", site_id)

            # Create client coordinator for this site
            client_coordinator = OmadaClientCoordinator(
                hass=hass,
                api_client=api_client,
                site_id=site_id,
                site_name=site_name,
                selected_client_macs=selected_client_macs,
                scan_interval=client_interval,
            )

            # Perform initial data fetch
            await client_coordinator.async_config_entry_first_refresh()
            client_coordinators.append(client_coordinator)

            _LOGGER.info(
                "Initialized client coordinator for site '%s' with %d/%d clients found",
                site_name,
                len(client_coordinator.data),
                len(selected_client_macs),
            )

    # Create app traffic coordinators for selected applications
    app_traffic_coordinators: list[OmadaAppTrafficCoordinator] = []
    selected_app_ids: list[str] = entry.data.get(CONF_SELECTED_APPLICATIONS, [])

    if selected_app_ids and selected_client_macs:
        _LOGGER.info(
            "Setting up app traffic tracking for %d apps across %d clients",
            len(selected_app_ids),
            len(selected_client_macs),
        )

        for site_id in selected_site_ids:
            site_info = sites_by_id.get(site_id)
            if not site_info:
                continue

            site_name = site_info.get("name", site_id)

            # Create app traffic coordinator for this site
            app_coordinator = OmadaAppTrafficCoordinator(
                hass=hass,
                api_client=api_client,
                site_id=site_id,
                site_name=site_name,
                selected_client_macs=selected_client_macs,
                selected_app_ids=selected_app_ids,
                scan_interval=app_interval,
            )

            # Perform initial data fetch
            await app_coordinator.async_config_entry_first_refresh()
            app_traffic_coordinators.append(app_coordinator)

            _LOGGER.info(
                "Initialized app traffic coordinator for site '%s' with %d clients",
                site_name,
                len(app_coordinator.data),
            )

    # Store API client and coordinators in runtime_data
    #
    # Check whether the API credentials have write access by performing a
    # non-destructive probe on the first site.  When the credentials are
    # viewer-only, controllable switches (PoE, LED) are not created.
    has_write_access = True
    if coordinators:
        first_site_id = next(iter(coordinators))
        has_write_access = await api_client.check_write_access(first_site_id)
        _LOGGER.info(
            "Write access check result: %s (checked site: %s)",
            "GRANTED" if has_write_access else "DENIED",
            first_site_id,
        )
        # Log total SSID count across all sites for SSID switch troubleshooting
        total_ssids = sum(len(c.data.get("ssids", [])) for c in coordinators.values())
        _LOGGER.info(
            "Total SSIDs across %d site(s): %d",
            len(coordinators),
            total_ssids,
        )

    # Register Site device entities for each configured site
    device_reg = dr.async_get(hass)
    site_devices: dict[str, dr.DeviceEntry] = {}
    for site_id, coordinator in coordinators.items():
        site_device = device_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"site_{site_id}")},
            name=f"{coordinator.site_name} - Site",
            manufacturer="TP-Link",
            model="Omada Site",
            configuration_url=entry.data[CONF_API_URL],
        )
        site_devices[site_id] = site_device
        _LOGGER.debug(
            "Registered Site device for site '%s' (%s)",
            coordinator.site_name,
            site_id,
        )

    entry.runtime_data = {
        "api_client": api_client,
        "coordinators": coordinators,
        "client_coordinators": client_coordinators,
        "app_traffic_coordinators": app_traffic_coordinators,
        "has_write_access": has_write_access,
        "site_devices": site_devices,
    }

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register diagnostic service
    async def debug_ssid_switches_service(call: Any) -> None:
        """Service to dump SSID switch diagnostic information."""
        config_entry_id = call.data.get("config_entry_id", entry.entry_id)

        # Find the config entry
        target_entry = hass.config_entries.async_get_entry(config_entry_id)
        if not target_entry or target_entry.domain != DOMAIN:
            _LOGGER.error(
                "Config entry %s not found or not an Omada integration",
                config_entry_id,
            )
            return

        runtime_data = target_entry.runtime_data
        coordinators = runtime_data.get("coordinators", {})
        has_write_access = runtime_data.get("has_write_access", False)
        site_devices = runtime_data.get("site_devices", {})

        _LOGGER.info("=== SSID Switch Diagnostic Info ===")
        _LOGGER.info("Config Entry: %s (%s)", target_entry.title, config_entry_id)
        _LOGGER.info("Write Access: %s", has_write_access)
        _LOGGER.info("Coordinators: %d", len(coordinators))
        _LOGGER.info("Site Devices: %d", len(site_devices))

        total_ssids = 0
        for site_id, coordinator in coordinators.items():
            ssids = coordinator.data.get("ssids", [])
            total_ssids += len(ssids)
            _LOGGER.info(
                "  Site '%s': %d SSIDs",
                site_id,
                len(ssids),
            )
            for ssid in ssids:
                _LOGGER.info(
                    "    - ID: %s, wlanId: %s, name: %s, broadcast: %s",
                    ssid.get("id", "missing"),
                    ssid.get("wlanId", "missing"),
                    ssid.get("name", "missing"),
                    ssid.get("broadcast", "missing"),
                )

        _LOGGER.info("Total SSIDs across all sites: %d", total_ssids)

        # Count actual SSID switch entities
        entity_reg = er.async_get(hass)
        ssid_switches = [
            ent
            for ent in entity_reg.entities.values()
            if ent.config_entry_id == config_entry_id
            and ent.domain == "switch"
            and "ssid" in ent.unique_id
        ]
        _LOGGER.info("SSID switch entities created: %d", len(ssid_switches))
        for ent in ssid_switches:
            _LOGGER.info("  - %s (%s)", ent.entity_id, ent.unique_id)

        _LOGGER.info("=== End SSID Switch Diagnostic Info ===")

    hass.services.async_register(
        DOMAIN,
        "debug_ssid_switches",
        debug_ssid_switches_service,
    )

    # Snapshot current data so the update listener can detect real config changes
    # vs. token-only updates.
    hass.data.setdefault(f"{DOMAIN}_prev_data", {})[entry.entry_id] = dict(entry.data)

    # Set up config entry update listener (skips reload on token-only changes)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry to unload

    Returns:
        True if unload was successful

    """
    _LOGGER.debug("Unloading Omada Open API integration")

    # Unload platforms
    unload_ok: bool = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Runtime data is automatically cleaned up when entry is unloaded
    # No need to manually remove it

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when it's updated.

    Only reload when configuration actually changes (sites, clients,
    applications, scan intervals).  Token-only updates are persisted by the
    API client and do not require a reload.

    Args:
        hass: Home Assistant instance
        entry: Config entry that was updated

    """
    # Keys that represent transient auth state — changes to only these
    # should NOT trigger a full reload.
    token_keys = {
        CONF_ACCESS_TOKEN,
        CONF_REFRESH_TOKEN,
        CONF_TOKEN_EXPIRES_AT,
        CONF_TOKEN_EXPIRES,
    }

    # Compare current runtime data snapshot with the new entry data.
    # If only token keys differ, skip the reload.
    prev_store: dict[str, dict[str, Any]] = hass.data.get(f"{DOMAIN}_prev_data", {})
    previous_data = prev_store.get(entry.entry_id, {})
    current_data = dict(entry.data)

    if previous_data:
        changed_keys = {
            k
            for k in current_data.keys() | previous_data.keys()
            if current_data.get(k) != previous_data.get(k)
        }
        if changed_keys and changed_keys <= token_keys:
            _LOGGER.debug("Skipping reload — only auth tokens changed")
            prev_store[entry.entry_id] = current_data
            return

    prev_store[entry.entry_id] = current_data

    # Clean up devices and entities that are no longer selected before reloading
    await _cleanup_devices(hass, entry)
    await _cleanup_entities(hass, entry)

    await hass.config_entries.async_reload(entry.entry_id)


async def _cleanup_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove devices that are no longer in the selected lists.

    Args:
        hass: Home Assistant instance
        entry: Config entry

    """
    device_registry = dr.async_get(hass)

    # Get currently selected items
    selected_client_macs = entry.data.get(CONF_SELECTED_CLIENTS, [])
    selected_site_ids = entry.data.get(CONF_SELECTED_SITES, [])

    # Normalize to uppercase with hyphens for comparison
    selected_client_macs_normalized = {
        normalize_client_mac(mac) for mac in selected_client_macs
    }
    selected_site_ids_normalized = {
        normalize_site_id(site_id) for site_id in selected_site_ids
    }

    # Get all devices for this config entry
    devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)

    removed_count = 0
    for device in devices:
        should_remove = True

        # Check if device is in selected lists
        for identifier in device.identifiers:
            if identifier[0] == DOMAIN:
                device_id = identifier[1].upper()

                # Keep if it's a selected client or site
                if (
                    device_id in selected_client_macs_normalized
                    or device_id in selected_site_ids_normalized
                ):
                    should_remove = False
                    break

        if should_remove:
            _LOGGER.info("Removing deselected device: %s", device.name)
            device_registry.async_remove_device(device.id)
            removed_count += 1

    if removed_count > 0:
        _LOGGER.info("Removed %d deselected device(s)", removed_count)


async def _cleanup_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove entities for deselected applications.

    Args:
        hass: Home Assistant instance
        entry: Config entry

    """
    entity_reg = er.async_get(hass)

    # Get currently selected applications
    selected_app_ids = entry.data.get(CONF_SELECTED_APPLICATIONS, [])

    if not selected_app_ids:
        # No apps selected, remove all app traffic entities
        _LOGGER.debug("No applications selected, will remove all app traffic entities")

    # Normalize app IDs for comparison
    selected_app_ids_normalized = {str(app_id) for app_id in selected_app_ids}

    # Get all entities for this config entry
    entities = er.async_entries_for_config_entry(entity_reg, entry.entry_id)

    removed_count = 0
    for entity in entities:
        # Check if this is an app traffic entity (format: {mac}_{app_id}_{upload/download}_app_traffic)
        if entity.unique_id and entity.unique_id.endswith("_app_traffic"):
            # Extract app_id from unique_id: "MAC_APPID_upload_app_traffic" or "MAC_APPID_download_app_traffic"
            parts = entity.unique_id.split("_")
            if len(parts) >= 4:  # MAC, APPID, upload/download, app, traffic
                # App ID is between MAC and metric type (upload/download)
                # Format: {mac}_{app_id}_{metric}_app_traffic
                # So app_id is parts[-3] (third from end)
                app_id = parts[-3]

                # Check if this app is still selected
                if app_id not in selected_app_ids_normalized:
                    _LOGGER.info(
                        "Removing entity for deselected application: %s (app_id: %s)",
                        entity.entity_id,
                        app_id,
                    )
                    entity_reg.async_remove(entity.entity_id)
                    removed_count += 1

    if removed_count > 0:
        _LOGGER.info(
            "Removed %d entity/entities for deselected applications", removed_count
        )


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device_entry: Any
) -> bool:
    """Remove a device from the integration.

    This is called when a user manually removes a device from the UI.
    It's also used to clean up devices that are no longer tracked.

    Args:
        hass: Home Assistant instance
        entry: Config entry
        device_entry: Device entry to remove

    Returns:
        True if the device can be removed, False otherwise

    """
    # Get the list of selected clients and sites
    selected_client_macs = entry.data.get(CONF_SELECTED_CLIENTS, [])
    selected_site_ids = entry.data.get(CONF_SELECTED_SITES, [])

    # Normalize MAC addresses to match format (with hyphens)
    selected_client_macs_normalized = {
        normalize_client_mac(mac) for mac in selected_client_macs
    }
    selected_site_ids_normalized = {
        normalize_site_id(site_id) for site_id in selected_site_ids
    }

    # Check if this device is still in the selected lists
    for identifier in device_entry.identifiers:
        if identifier[0] == DOMAIN:
            device_id = identifier[1].upper()

            # Check if it's a selected client (client devices use MAC format)
            if device_id in selected_client_macs_normalized:
                _LOGGER.debug(
                    "Device %s is still a selected client, not removing", device_id
                )
                return False

            # Check if it's a selected site
            if device_id in selected_site_ids_normalized:
                _LOGGER.debug(
                    "Device %s is still a selected site, not removing", device_id
                )
                return False

    # Device is not in any selected list, allow removal
    _LOGGER.info("Allowing removal of device %s", device_entry.name)
    return True
