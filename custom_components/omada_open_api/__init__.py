"""The Omada Open API integration."""

from __future__ import annotations

import datetime as dt
import logging
import ssl
from typing import TYPE_CHECKING, Any

import aiohttp
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_VERIFY_SSL, Platform
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    ServiceValidationError,
)
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from homeassistant.helpers.aiohttp_client import (
    async_create_clientsession,
    async_get_clientsession,
)

from .api import OmadaApiAuthError, OmadaApiClient, OmadaApiError
from .auth import WebSessionAuth
from .clients import normalize_client_mac
from .const import (
    AUTH_MODE_WEB_SESSION,
    CONF_ACCESS_TOKEN,
    CONF_API_URL,
    CONF_APP_SCAN_INTERVAL,
    CONF_AUTH_MODE,
    CONF_AUTO_DISCOVER_CLIENT_TRACKERS,
    CONF_CLIENT_ID,
    CONF_CLIENT_SCAN_INTERVAL,
    CONF_CLIENT_SECRET,
    CONF_CONTROLLER_TYPE,
    CONF_DEVICE_SCAN_INTERVAL,
    CONF_DISCONNECT_TIMEOUT,
    CONF_ENABLE_DEVICE_RADIO_UTILIZATION_SENSORS,
    CONF_ENABLE_THREAT_HEATMAP_SENSORS,
    CONF_ENABLE_VPN_SENSORS,
    CONF_ENABLE_WAN_SPEED_TEST,
    CONF_OMADA_ID,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_SELECTED_APPLICATIONS,
    CONF_SELECTED_CLIENTS,
    CONF_SELECTED_SITES,
    CONF_STATS_SCAN_INTERVAL,
    CONF_TOKEN_EXPIRES,
    CONF_TOKEN_EXPIRES_AT,
    CONF_USERNAME,
    DEFAULT_APP_SCAN_INTERVAL,
    DEFAULT_CLIENT_SCAN_INTERVAL,
    DEFAULT_DEVICE_SCAN_INTERVAL,
    DEFAULT_DISCONNECT_TIMEOUT,
    DEFAULT_STATS_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
    THREAT_HEATMAP_INTERVALS,
    resolve_verify_ssl,
)
from .coordinator import (
    OmadaAppTrafficCoordinator,
    OmadaClientCoordinator,
    OmadaDeviceStatsCoordinator,
    OmadaSiteCoordinator,
    OmadaThreatHeatmapCoordinator,
    OmadaWanSpeedTestCoordinator,
)
from .migrations import (
    migrate_data_to_options,
    migrate_merged_devices,
    migrate_wan_speed_test_button_unique_ids,
)
from .registry_cleanup import (
    can_remove_device,
    cleanup_devices,
    cleanup_entities,
    setup_stale_infra_device_pruning,
)
from .services import async_setup_services
from .types import OmadaConfigEntry, OmadaRuntimeData

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)  # pylint: disable=invalid-name

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

    async_setup_services(hass)
    return True


def _is_certificate_error(err: BaseException) -> bool:
    """Return True if an exception's cause chain contains a TLS certificate error.

    Args:
        err: Exception whose ``__cause__``/``__context__`` chain is inspected.

    Returns:
        True when the chain contains an ``ssl.SSLCertVerificationError`` or an
        ``aiohttp.ClientConnectorCertificateError``.

    """
    seen: set[int] = set()
    current: BaseException | None = err
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(
            current,
            (ssl.SSLCertVerificationError, aiohttp.ClientConnectorCertificateError),
        ):
            return True
        current = current.__cause__ or current.__context__
    return False


def _is_transient_connection_error(err: BaseException) -> bool:
    """Detect temporary controller reachability failures wrapped in OmadaApiError.

    Authentication, application errors and TLS verification errors must not
    be retried as connectivity problems. ConfigEntryNotReady lets HA retry
    startup with its normal backoff when a local controller is still starting.
    """
    if _is_certificate_error(err):
        return False
    current: BaseException | None = err
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (aiohttp.ClientConnectionError, TimeoutError, OSError)):
            return True
        current = current.__cause__ or current.__context__
    return False


async def _async_create_wan_speed_test_coordinators(
    hass: HomeAssistant,
    api_client: OmadaApiClient,
    coordinators: dict[str, OmadaSiteCoordinator],
) -> dict[tuple[str, str], OmadaWanSpeedTestCoordinator]:
    """Create independently-polled speed-test coordinators for gateways."""
    result: dict[tuple[str, str], OmadaWanSpeedTestCoordinator] = {}
    for site_coordinator in coordinators.values():
        for gateway_mac, device in site_coordinator.data.get("devices", {}).items():
            if device.get("type", "").lower() != "gateway":
                continue
            coordinator = OmadaWanSpeedTestCoordinator(
                hass, api_client, site_coordinator.site_id, gateway_mac
            )
            await coordinator.async_refresh()
            result[(site_coordinator.site_id, gateway_mac)] = coordinator
    return result


async def _async_setup_wan_speed_test(
    hass: HomeAssistant,
    entry: OmadaConfigEntry,
    api_client: OmadaApiClient,
    coordinators: dict[str, OmadaSiteCoordinator],
) -> dict[tuple[str, str], OmadaWanSpeedTestCoordinator]:
    """Create optional WAN speed-test coordinators and migrate their IDs."""
    if not entry.options.get(CONF_ENABLE_WAN_SPEED_TEST, True):
        return {}

    wan_speed_test_coordinators = await _async_create_wan_speed_test_coordinators(
        hass, api_client, coordinators
    )
    migrate_wan_speed_test_button_unique_ids(hass, wan_speed_test_coordinators)
    return wan_speed_test_coordinators


def _entry_auth_mode(entry: OmadaConfigEntry) -> str | None:
    """Return the auth mode, inferring Fusion for entries without the key."""
    auth_mode: str | None = entry.data.get(
        CONF_AUTH_MODE, AUTH_MODE_WEB_SESSION if CONF_USERNAME in entry.data else None
    )
    return auth_mode


def _create_api_client(hass: HomeAssistant, entry: OmadaConfigEntry) -> OmadaApiClient:
    """Create the API client for the entry's auth mode."""
    if _entry_auth_mode(entry) == AUTH_MODE_WEB_SESSION:
        # Fusion Gateway: web-session authentication
        # Fusion controllers are accessed by IP — aiohttp's default safe
        # cookie jar refuses to store cookies for IP-based URLs, so we
        # create a session with unsafe=True. Home Assistant registers the
        # cleanup on entry unload (also when setup fails) and on shutdown.
        session = async_create_clientsession(
            hass, verify_ssl=False, cookie_jar=aiohttp.CookieJar(unsafe=True)
        )

        async def _fusion_token_callback(*_args: str) -> None:
            """No-op for Fusion — session is re-created from credentials."""

        auth = WebSessionAuth(
            session=session,
            token_update_callback=_fusion_token_callback,
            api_url=entry.data[CONF_API_URL],
            omada_id=entry.data[CONF_OMADA_ID],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
        )
        return OmadaApiClient(
            session=session,
            token_update_callback=_fusion_token_callback,
            api_url=entry.data[CONF_API_URL],
            omada_id=entry.data[CONF_OMADA_ID],
            client_id="",
            client_secret="",
            access_token="",
            refresh_token="",
            token_expires_at=dt.datetime.now(dt.UTC),
            auth=auth,
        )

    # Traditional OpenAPI: client_credentials authentication
    session = async_get_clientsession(
        hass,
        verify_ssl=resolve_verify_ssl(
            entry.data.get(CONF_CONTROLLER_TYPE),
            entry.data.get(CONF_VERIFY_SSL),
        ),
    )
    token_expires_at = dt.datetime.fromisoformat(entry.data[CONF_TOKEN_EXPIRES_AT])

    async def _token_update_callback(
        access_token: str, refresh_token: str, expires_at_iso: str
    ) -> None:
        """Persist updated tokens to the config entry."""
        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                CONF_ACCESS_TOKEN: access_token,
                CONF_REFRESH_TOKEN: refresh_token,
                CONF_TOKEN_EXPIRES_AT: expires_at_iso,
            },
        )

    return OmadaApiClient(
        session=session,
        token_update_callback=_token_update_callback,
        api_url=entry.data[CONF_API_URL],
        omada_id=entry.data[CONF_OMADA_ID],
        client_id=entry.data[CONF_CLIENT_ID],
        client_secret=entry.data[CONF_CLIENT_SECRET],
        access_token=entry.data[CONF_ACCESS_TOKEN],
        refresh_token=entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=token_expires_at,
    )


async def _async_connect(
    hass: HomeAssistant, entry: OmadaConfigEntry
) -> tuple[OmadaApiClient, list[dict[str, Any]]]:
    """Create the API client and read the sites, which also checks the login.

    Raises:
        ConfigEntryAuthFailed: If the controller rejects the credentials
        ConfigEntryNotReady: If the controller cannot be reached (yet)

    """
    try:
        api_client = _create_api_client(hass, entry)
        # Test connection and refresh token if needed
        sites = await api_client.get_sites()
        _LOGGER.info("Successfully connected to Omada API, found %d sites", len(sites))

    except OmadaApiAuthError as err:
        if _is_transient_connection_error(err):
            raise ConfigEntryNotReady(
                translation_domain=DOMAIN, translation_key="controller_unreachable"
            ) from err
        _LOGGER.exception("Authentication failed during setup")
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN, translation_key="auth_failed"
        ) from err
    except OmadaApiError as err:
        if _is_certificate_error(err):
            _LOGGER.warning(
                "TLS certificate verification failed for %s. Disable 'Verify "
                "TLS certificate' in the integration's reconfigure settings "
                "if this controller uses a self-signed certificate.",
                entry.data[CONF_API_URL],
            )
            raise ConfigEntryNotReady(
                translation_domain=DOMAIN,
                translation_key="certificate_verification_failed",
            ) from err
        if _is_transient_connection_error(err):
            raise ConfigEntryNotReady(
                translation_domain=DOMAIN, translation_key="controller_unreachable"
            ) from err
        raise
    except (TimeoutError, OSError) as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key="cannot_connect"
        ) from err
    return api_client, sites


def _selected_sites(
    entry: OmadaConfigEntry, sites: list[dict[str, Any]]
) -> list[tuple[str, dict[str, Any]]]:
    """Return (selected site ID, site) for every selected site still present.

    A Fusion gateway has a single site whose ID may change after a firmware
    update, so a missing selected site falls back to that only site.
    """
    sites_by_id = {site["siteId"]: site for site in sites}
    selected: list[tuple[str, dict[str, Any]]] = []
    for site_id in entry.data.get(CONF_SELECTED_SITES, []):
        site_info = sites_by_id.get(site_id)
        if (
            not site_info
            and len(sites) == 1
            and _entry_auth_mode(entry) == AUTH_MODE_WEB_SESSION
        ):
            site_info = sites[0]
            _LOGGER.info(
                "Site %s not found, using only available site %s (Fusion fallback)",
                site_id,
                site_info["siteId"],
            )
        if not site_info:
            _LOGGER.warning("Selected site %s not found in available sites", site_id)
            continue
        selected.append((site_id, site_info))
    return selected


async def _async_create_site_coordinators(
    hass: HomeAssistant,
    entry: OmadaConfigEntry,
    api_client: OmadaApiClient,
    sites: list[tuple[str, dict[str, Any]]],
) -> dict[str, OmadaSiteCoordinator]:
    """Create and refresh one device coordinator per selected site."""
    coordinators: dict[str, OmadaSiteCoordinator] = {}
    for site_id, site_info in sites:
        site_name = site_info.get("name", site_id)
        coordinator = OmadaSiteCoordinator(
            hass=hass,
            api_client=api_client,
            # Requests go to the site the controller lists now; identities keep
            # the selected ID so a Fusion site ID change orphans no entity.
            site_id=site_info["siteId"],
            entry_site_id=site_id,
            site_name=site_name,
            scan_interval=entry.options.get(
                CONF_DEVICE_SCAN_INTERVAL, DEFAULT_DEVICE_SCAN_INTERVAL
            ),
            enable_vpn_status=entry.options.get(CONF_ENABLE_VPN_SENSORS, True),
            enable_radio_utilization=entry.options.get(
                CONF_ENABLE_DEVICE_RADIO_UTILIZATION_SENSORS, True
            ),
        )

        # Perform initial data fetch
        await coordinator.async_config_entry_first_refresh()
        coordinators[site_id] = coordinator

        ssids = coordinator.data.get("ssids", [])
        _LOGGER.info(
            "Initialized coordinator for site '%s' with %d devices and %d SSIDs",
            site_name,
            len(coordinator.data.get("devices", {})),
            len(ssids),
        )
        _LOGGER.debug(
            "SSIDs for site '%s': %s",
            site_name,
            [s.get("name", "Unknown") for s in ssids],
        )
    return coordinators


def _register_site_devices(
    hass: HomeAssistant,
    entry: OmadaConfigEntry,
    coordinators: dict[str, OmadaSiteCoordinator],
) -> dict[str, dr.DeviceEntry]:
    """Register a Site device for each configured site.

    This happens before client coordinators are created so a client with no
    identified parent AP/switch/gateway can link its via_device_id to the
    site device's real (always-registered) id. See GH #69.
    """
    device_reg = dr.async_get(hass)
    site_devices: dict[str, dr.DeviceEntry] = {}
    for site_id, coordinator in coordinators.items():
        site_devices[site_id] = device_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"site_{site_id}")},
            name=f"{coordinator.site_name} - Site",
            manufacturer="TP-Link",
            model="Omada Site",
            configuration_url=entry.data[CONF_API_URL],
        )
        _LOGGER.debug(
            "Registered Site device for site '%s' (%s)",
            coordinator.site_name,
            site_id,
        )
    return site_devices


async def _async_create_client_coordinators(
    hass: HomeAssistant,
    entry: OmadaConfigEntry,
    api_client: OmadaApiClient,
    sites: list[tuple[str, dict[str, Any]]],
    site_devices: dict[str, dr.DeviceEntry],
) -> list[OmadaClientCoordinator]:
    """Create and refresh client coordinators for the selected clients."""
    selected_client_macs: list[str] = entry.options.get(CONF_SELECTED_CLIENTS, [])
    if not selected_client_macs:
        return []

    _LOGGER.info("Setting up tracking for %d clients", len(selected_client_macs))
    client_coordinators: list[OmadaClientCoordinator] = []
    for site_id, site_info in sites:
        site_name = site_info.get("name", site_id)
        client_site_device = site_devices.get(site_id)
        client_coordinator = OmadaClientCoordinator(
            hass=hass,
            api_client=api_client,
            site_id=site_id,
            site_name=site_name,
            selected_client_macs=selected_client_macs,
            scan_interval=entry.options.get(
                CONF_CLIENT_SCAN_INTERVAL, DEFAULT_CLIENT_SCAN_INTERVAL
            ),
            disconnect_timeout=entry.options.get(
                CONF_DISCONNECT_TIMEOUT, DEFAULT_DISCONNECT_TIMEOUT
            ),
            site_device_id=client_site_device.id if client_site_device else None,
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
    return client_coordinators


async def _async_create_app_traffic_coordinators(
    hass: HomeAssistant,
    entry: OmadaConfigEntry,
    api_client: OmadaApiClient,
    sites: list[tuple[str, dict[str, Any]]],
) -> list[OmadaAppTrafficCoordinator]:
    """Create and refresh app traffic coordinators for the selected apps."""
    selected_client_macs: list[str] = entry.options.get(CONF_SELECTED_CLIENTS, [])
    selected_app_ids: list[str] = entry.options.get(CONF_SELECTED_APPLICATIONS, [])
    if not (selected_app_ids and selected_client_macs):
        return []

    _LOGGER.info(
        "Setting up app traffic tracking for %d apps across %d clients",
        len(selected_app_ids),
        len(selected_client_macs),
    )
    app_traffic_coordinators: list[OmadaAppTrafficCoordinator] = []
    for site_id, site_info in sites:
        site_name = site_info.get("name", site_id)
        app_coordinator = OmadaAppTrafficCoordinator(
            hass=hass,
            api_client=api_client,
            site_id=site_id,
            site_name=site_name,
            selected_client_macs=selected_client_macs,
            selected_app_ids=selected_app_ids,
            scan_interval=entry.options.get(
                CONF_APP_SCAN_INTERVAL, DEFAULT_APP_SCAN_INTERVAL
            ),
        )

        # Perform initial data fetch
        await app_coordinator.async_config_entry_first_refresh()
        app_traffic_coordinators.append(app_coordinator)

        _LOGGER.info(
            "Initialized app traffic coordinator for site '%s' with %d clients",
            site_name,
            len(app_coordinator.data),
        )
    return app_traffic_coordinators


def _update_dpi_gateway_issue(
    hass: HomeAssistant,
    entry: OmadaConfigEntry,
    coordinators: dict[str, OmadaSiteCoordinator],
) -> None:
    """Raise or clear the repair issue for app tracking without a gateway.

    DPI-based app tracking requires a gateway in the Omada network.
    """
    if entry.options.get(CONF_SELECTED_APPLICATIONS, []) and coordinators:
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
            return
    # No apps selected, or a gateway is present — clear any previous issue.
    ir.async_delete_issue(hass, DOMAIN, "dpi_no_gateway")


async def _async_create_device_stats_coordinators(
    hass: HomeAssistant,
    entry: OmadaConfigEntry,
    api_client: OmadaApiClient,
    coordinators: dict[str, OmadaSiteCoordinator],
) -> list[OmadaDeviceStatsCoordinator]:
    """Create and refresh device stats coordinators for daily traffic."""
    stats_interval = entry.options.get(
        CONF_STATS_SCAN_INTERVAL, DEFAULT_STATS_SCAN_INTERVAL
    )
    device_stats_coordinators: list[OmadaDeviceStatsCoordinator] = []
    for site_coordinator in coordinators.values():
        stats_coordinator = OmadaDeviceStatsCoordinator(
            hass=hass,
            api_client=api_client,
            site_coordinator=site_coordinator,
            scan_interval=stats_interval,
        )
        await stats_coordinator.async_config_entry_first_refresh()
        device_stats_coordinators.append(stats_coordinator)

        _LOGGER.info(
            "Initialized device stats coordinator for site '%s' with %d devices",
            site_coordinator.site_name,
            len(stats_coordinator.data),
        )
    return device_stats_coordinators


async def _async_create_threat_heatmap_coordinators(
    hass: HomeAssistant,
    entry: OmadaConfigEntry,
    api_client: OmadaApiClient,
    coordinators: dict[str, OmadaSiteCoordinator],
) -> list[OmadaThreatHeatmapCoordinator]:
    """Create threat heatmap coordinators (daily/weekly/monthly per site).

    An unsupported/erroring endpoint never blocks setup — see
    OmadaThreatHeatmapCoordinator._async_update_data.
    """
    threat_heatmap_coordinators: list[OmadaThreatHeatmapCoordinator] = []
    if not entry.options.get(CONF_ENABLE_THREAT_HEATMAP_SENSORS, True):
        return threat_heatmap_coordinators
    for site_coordinator in coordinators.values():
        for window in THREAT_HEATMAP_INTERVALS:
            heatmap_coordinator = OmadaThreatHeatmapCoordinator(
                hass=hass,
                api_client=api_client,
                site_id=site_coordinator.site_id,
                entry_site_id=site_coordinator.entry_site_id,
                site_name=site_coordinator.site_name,
                window=window,
            )
            await heatmap_coordinator.async_config_entry_first_refresh()
            threat_heatmap_coordinators.append(heatmap_coordinator)
    return threat_heatmap_coordinators


async def _async_check_write_access(
    hass: HomeAssistant,
    api_client: OmadaApiClient,
    coordinators: dict[str, OmadaSiteCoordinator],
) -> bool:
    """Probe whether the credentials may write, and raise/clear the repair issue.

    A non-destructive probe on the first site. When the credentials are
    viewer-only, controllable switches (PoE, LED) are not created.
    """
    if not coordinators:
        return True
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
    return has_write_access


async def async_setup_entry(hass: HomeAssistant, entry: OmadaConfigEntry) -> bool:
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
    migrate_data_to_options(hass, entry)

    # Migrate away historical multi-MAC merged devices (pre-v1.8.1 bug) —
    # must run before platforms load so clean per-MAC devices are recreated
    # in this same setup pass.
    migrate_merged_devices(hass, entry)

    api_client, all_sites = await _async_connect(hass, entry)
    # Reuse the sites already fetched during setup. A second request can fail
    # when the controller is still starting, and is otherwise redundant.
    sites = _selected_sites(entry, all_sites)

    coordinators = await _async_create_site_coordinators(hass, entry, api_client, sites)
    site_devices = _register_site_devices(hass, entry, coordinators)
    # Client and app tracking only run for sites the controller still lists
    # under their selected ID, not for the Fusion single-site fallback.
    listed_sites = [(sid, info) for sid, info in sites if info["siteId"] == sid]
    client_coordinators = await _async_create_client_coordinators(
        hass, entry, api_client, listed_sites, site_devices
    )
    app_traffic_coordinators = await _async_create_app_traffic_coordinators(
        hass, entry, api_client, listed_sites
    )
    _update_dpi_gateway_issue(hass, entry, coordinators)
    wan_speed_test_coordinators = await _async_setup_wan_speed_test(
        hass, entry, api_client, coordinators
    )
    device_stats_coordinators = await _async_create_device_stats_coordinators(
        hass, entry, api_client, coordinators
    )
    threat_heatmap_coordinators = await _async_create_threat_heatmap_coordinators(
        hass, entry, api_client, coordinators
    )
    has_write_access = await _async_check_write_access(hass, api_client, coordinators)

    entry.runtime_data = OmadaRuntimeData(
        api_client=api_client,
        coordinators=coordinators,
        client_coordinators=client_coordinators,
        app_traffic_coordinators=app_traffic_coordinators,
        device_stats_coordinators=device_stats_coordinators,
        has_write_access=has_write_access,
        site_devices=site_devices,
        prev_data=dict(entry.data),
        prev_options=dict(entry.options),
        threat_heatmap_coordinators=threat_heatmap_coordinators,
        wan_speed_test_coordinators=wan_speed_test_coordinators,
    )

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    setup_stale_infra_device_pruning(hass, entry, coordinators)

    # Set up config entry update listener (skips reload on token-only changes)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: OmadaConfigEntry) -> bool:
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


async def async_reload_entry(hass: HomeAssistant, entry: OmadaConfigEntry) -> None:
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
    rd: OmadaRuntimeData | None = getattr(entry, "runtime_data", None)
    if rd:
        previous_data = rd.prev_data
        previous_options = rd.prev_options
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
            if rd:
                rd.prev_data = current_data
            return

    # Clean up devices and entities that are no longer selected before reloading.
    # Must run BEFORE updating prev snapshots so cleanup can compute the diff.
    await cleanup_devices(hass, entry)
    await cleanup_entities(hass, entry)

    if rd:
        rd.prev_data = current_data
        rd.prev_options = current_options

    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: OmadaConfigEntry, device_entry: dr.DeviceEntry
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
    return can_remove_device(entry, device_entry)
