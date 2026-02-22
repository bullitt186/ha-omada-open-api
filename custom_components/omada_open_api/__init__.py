"""The Omada Open API integration."""

from __future__ import annotations

import datetime as dt
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.const import Platform
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    ServiceValidationError,
)
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)

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
    Also registers Omada diagnostic services (see checklist/rules: action-setup).
    """

    # Register diagnostic service globally (action-setup rule)
    async def debug_ssid_switches_service(call: Any) -> None:
        """Service to dump SSID switch diagnostic information."""
        config_entry_id = call.data.get("config_entry_id")
        if not config_entry_id:
            _LOGGER.error("config_entry_id must be provided to the service call")
            return
        target_entry = hass.config_entries.async_get_entry(config_entry_id)
        if not target_entry or target_entry.domain != DOMAIN:
            _LOGGER.error(
                "Config entry %s not found or not an Omada integration",
                config_entry_id,
            )
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="config_entry_not_found",
                translation_placeholders={"config_entry_id": config_entry_id},
            )
        runtime_data = getattr(target_entry, "runtime_data", None)
        if not runtime_data:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_runtime_data",
                translation_placeholders={"config_entry_id": config_entry_id},
            )
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
    return True


# Keys that belong in entry.options rather than entry.data.
_OPTIONS_KEYS = {
    CONF_SELECTED_CLIENTS,
    CONF_SELECTED_APPLICATIONS,
    CONF_DEVICE_SCAN_INTERVAL,
    CONF_CLIENT_SCAN_INTERVAL,
    CONF_APP_SCAN_INTERVAL,
}


def _migrate_data_to_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Move user-preference keys from entry.data to entry.options.

    Older versions stored scan intervals and selections in entry.data.
    This one-time migration moves them to entry.options where they belong.

    Args:
        hass: Home Assistant instance
        entry: Config entry to migrate

    """
    migrated: dict[str, Any] = {}
    for key in _OPTIONS_KEYS:
        if key in entry.data:
            migrated[key] = entry.data[key]

    if not migrated:
        return

    _LOGGER.info("Migrating %d key(s) from entry.data to entry.options", len(migrated))

    # Remove migrated keys from data
    new_data = {k: v for k, v in entry.data.items() if k not in _OPTIONS_KEYS}

    # Merge into existing options (existing options take precedence)
    new_options = {**migrated, **dict(entry.options)}

    hass.config_entries.async_update_entry(
        entry,
        data=new_data,
        options=new_options,
    )


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

    # Migrate legacy config: move user-preference keys from data to options.
    _migrate_data_to_options(hass, entry)

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
    except (TimeoutError, OSError) as err:
        raise ConfigEntryNotReady(
            "Unable to connect to Omada API. Will retry."
        ) from err

    # Create coordinators for each selected site
    coordinators: dict[str, OmadaSiteCoordinator] = {}
    selected_site_ids: list[str] = entry.data.get(CONF_SELECTED_SITES, [])

    # Get configured scan intervals from options
    device_interval = entry.options.get(
        CONF_DEVICE_SCAN_INTERVAL, DEFAULT_DEVICE_SCAN_INTERVAL
    )
    client_interval = entry.options.get(
        CONF_CLIENT_SCAN_INTERVAL, DEFAULT_CLIENT_SCAN_INTERVAL
    )
    app_interval = entry.options.get(CONF_APP_SCAN_INTERVAL, DEFAULT_APP_SCAN_INTERVAL)

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
    selected_client_macs: list[str] = entry.options.get(CONF_SELECTED_CLIENTS, [])

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
    selected_app_ids: list[str] = entry.options.get(CONF_SELECTED_APPLICATIONS, [])

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

    # Raise / clear a repair issue when DPI-based app tracking is configured
    # but no gateway is present.  DPI requires a gateway in the Omada network.
    if selected_app_ids and coordinators:
        has_gateway = any(
            dev.get("type", "").lower() == "gateway"
            for coord in coordinators.values()
            for dev in coord.data.get("devices", {}).values()
        )
        if not has_gateway:
            ir.async_create_issue(
                hass,
                DOMAIN,
                "dpi_no_gateway",
                is_fixable=False,
                issue_domain=DOMAIN,
                severity=ir.IssueSeverity.WARNING,
                translation_key="dpi_no_gateway",
            )
        else:
            ir.async_delete_issue(hass, DOMAIN, "dpi_no_gateway")
    else:
        # No apps selected — clear any previous issue.
        ir.async_delete_issue(hass, DOMAIN, "dpi_no_gateway")

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

        # Raise / clear a repair issue for viewer-only credentials.
        if not has_write_access:
            ir.async_create_issue(
                hass,
                DOMAIN,
                "write_access_denied",
                is_fixable=False,
                issue_domain=DOMAIN,
                severity=ir.IssueSeverity.WARNING,
                translation_key="write_access_denied",
            )
        else:
            ir.async_delete_issue(hass, DOMAIN, "write_access_denied")

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
        "prev_data": dict(entry.data),
        "prev_options": dict(entry.options),
    }

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

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

    # Compare previous data/options snapshots with current values.
    # If only token keys in data differ and options are unchanged, skip reload.
    previous_data: dict[str, Any] = {}
    previous_options: dict[str, Any] = {}
    runtime_data = getattr(entry, "runtime_data", None)
    if runtime_data:
        previous_data = runtime_data.get("prev_data", {})
        previous_options = runtime_data.get("prev_options", {})
    current_data = dict(entry.data)
    current_options = dict(entry.options)

    options_changed = current_options != previous_options

    if previous_data and not options_changed:
        changed_keys = {
            k
            for k in current_data.keys() | previous_data.keys()
            if current_data.get(k) != previous_data.get(k)
        }
        if changed_keys and changed_keys <= token_keys:
            _LOGGER.debug("Skipping reload — only auth tokens changed")
            if runtime_data:
                runtime_data["prev_data"] = current_data
            return

    # Clean up devices and entities that are no longer selected before reloading.
    # Must run BEFORE updating prev snapshots so cleanup can compute the diff.
    await _cleanup_devices(hass, entry)
    await _cleanup_entities(hass, entry)

    if runtime_data:
        runtime_data["prev_data"] = current_data
        runtime_data["prev_options"] = current_options

    await hass.config_entries.async_reload(entry.entry_id)


async def _cleanup_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove devices for clients/sites that were deselected.

    Only removes devices whose identifier matches a previously-selected
    client MAC or site that is no longer selected.  Infrastructure devices
    (router, switches, APs) are never touched — they are managed by the
    coordinator and will be re-created during setup.

    Args:
        hass: Home Assistant instance
        entry: Config entry

    """
    runtime_data = getattr(entry, "runtime_data", None)
    if not runtime_data:
        return

    prev_options: dict[str, Any] = runtime_data.get("prev_options", {})
    prev_data: dict[str, Any] = runtime_data.get("prev_data", {})

    # Compute deselected clients (previously selected but no longer)
    prev_clients = {
        normalize_client_mac(m) for m in prev_options.get(CONF_SELECTED_CLIENTS, [])
    }
    curr_clients = {
        normalize_client_mac(m) for m in entry.options.get(CONF_SELECTED_CLIENTS, [])
    }
    deselected_clients = prev_clients - curr_clients

    # Compute deselected sites
    prev_sites = {normalize_site_id(s) for s in prev_data.get(CONF_SELECTED_SITES, [])}
    curr_sites = {normalize_site_id(s) for s in entry.data.get(CONF_SELECTED_SITES, [])}
    deselected_sites = prev_sites - curr_sites

    if not deselected_clients and not deselected_sites:
        return

    device_registry = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)

    removed_count = 0
    for device in devices:
        for identifier in device.identifiers:
            if identifier[0] != DOMAIN:
                continue
            device_id = identifier[1].upper()

            # Remove deselected client devices
            if device_id in deselected_clients:
                _LOGGER.info("Removing deselected client device: %s", device.name)
                device_registry.async_remove_device(device.id)
                removed_count += 1
                break

            # Remove deselected site devices (identifier: "site_{id}")
            if device_id.startswith("SITE_"):
                raw_site_id = device_id[5:]  # Strip "SITE_" prefix
                if raw_site_id in deselected_sites:
                    _LOGGER.info("Removing deselected site device: %s", device.name)
                    device_registry.async_remove_device(device.id)
                    removed_count += 1
                    break

    if removed_count > 0:
        _LOGGER.info("Removed %d deselected device(s)", removed_count)


async def _cleanup_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove entities for applications that were deselected.

    Only removes app-traffic sensor entities whose application was
    previously selected but is no longer in the current selection.

    Args:
        hass: Home Assistant instance
        entry: Config entry

    """
    runtime_data = getattr(entry, "runtime_data", None)
    if not runtime_data:
        return

    prev_options: dict[str, Any] = runtime_data.get("prev_options", {})

    prev_apps = {str(a) for a in prev_options.get(CONF_SELECTED_APPLICATIONS, [])}
    curr_apps = {str(a) for a in entry.options.get(CONF_SELECTED_APPLICATIONS, [])}
    deselected_apps = prev_apps - curr_apps

    if not deselected_apps:
        return

    entity_reg = er.async_get(hass)
    entities = er.async_entries_for_config_entry(entity_reg, entry.entry_id)

    removed_count = 0
    for entity in entities:
        # App traffic entities: "{mac}_{app_id}_{upload|download}_app_traffic"
        if not (entity.unique_id and entity.unique_id.endswith("_app_traffic")):
            continue

        parts = entity.unique_id.split("_")
        # parts: [mac, app_id, metric, "app", "traffic"]  (5 elements minimum)
        if len(parts) >= 5:
            app_id = parts[-4]  # app_id is 4th from end

            if app_id in deselected_apps:
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
    selected_client_macs = entry.options.get(CONF_SELECTED_CLIENTS, [])
    selected_site_ids = entry.data.get(CONF_SELECTED_SITES, [])

    # Normalize MAC addresses to match format (with hyphens)
    selected_client_macs_normalized = {
        normalize_client_mac(mac) for mac in selected_client_macs
    }
    selected_site_ids_normalized = {
        normalize_site_id(site_id) for site_id in selected_site_ids
    }

    # Collect all infrastructure device MACs still reported by coordinators.
    # Blocking removal of live devices prevents accidental deletion of
    # devices that would immediately reappear on the next poll.
    active_device_macs: set[str] = set()
    runtime_data = getattr(entry, "runtime_data", None)
    if runtime_data:
        for coordinator in runtime_data.get("coordinators", {}).values():
            if coordinator.data:
                for mac in coordinator.data.get("devices", {}):
                    active_device_macs.add(mac.upper())

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

            # Check if it's a selected site (identifier: "site_{id}")
            if device_id.startswith("SITE_"):
                raw_site_id = device_id[5:]  # Strip "SITE_" prefix
                if raw_site_id in selected_site_ids_normalized:
                    _LOGGER.debug(
                        "Device %s is still a selected site, not removing",
                        device_id,
                    )
                    return False

            # Block removal of infrastructure devices still in coordinator data
            if device_id in active_device_macs:
                _LOGGER.debug(
                    "Device %s is still active in coordinator data, not removing",
                    device_id,
                )
                return False

    # Device is not in any selected list, allow removal
    _LOGGER.info("Allowing removal of device %s", device_entry.name)
    return True
