"""The Omada Open API integration."""

from __future__ import annotations

import datetime as dt
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryAuthFailed

from .api import OmadaApiAuthError, OmadaApiClient
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_API_URL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_OMADA_ID,
    CONF_REFRESH_TOKEN,
    CONF_SELECTED_APPLICATIONS,
    CONF_SELECTED_CLIENTS,
    CONF_SELECTED_SITES,
    CONF_TOKEN_EXPIRES_AT,
    DOMAIN,
)
from .coordinator import (
    OmadaAppTrafficCoordinator,
    OmadaClientCoordinator,
    OmadaSiteCoordinator,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Platforms to set up
PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the Omada Open API component.

    This integration only supports config flow setup.
    YAML configuration is not supported.
    """
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:  # pylint: disable=too-many-statements
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
        )

        # Perform initial data fetch
        await coordinator.async_config_entry_first_refresh()
        coordinators[site_id] = coordinator

        _LOGGER.info(
            "Initialized coordinator for site '%s' with %d devices",
            site_name,
            len(coordinator.data.get("devices", {})),
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
    entry.runtime_data = {
        "api_client": api_client,
        "coordinators": coordinators,
        "client_coordinators": client_coordinators,
        "app_traffic_coordinators": app_traffic_coordinators,
    }

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Set up config entry update listener for token updates
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

    Args:
        hass: Home Assistant instance
        entry: Config entry that was updated

    """
    await hass.config_entries.async_reload(entry.entry_id)
