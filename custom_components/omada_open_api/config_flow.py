"""Config flow for Omada Open API integration."""

from __future__ import annotations

import datetime as dt
import logging
from typing import TYPE_CHECKING, Any

import aiohttp
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_VERIFY_SSL
from homeassistant.core import callback
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers.aiohttp_client import (
    async_create_clientsession,
    async_get_clientsession,
)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
import voluptuous as vol

from .api import OmadaApiClient, OmadaApiError, async_get_controller_id
from .auth import ClientCredentialsAuth, OmadaAuthStrategy, WebSessionAuth
from .clients import normalize_client_mac
from .const import (
    AUTH_MODE_OPENAPI,
    AUTH_MODE_WEB_SESSION,
    CONF_ACCESS_TOKEN,
    CONF_API_URL,
    CONF_APP_SCAN_INTERVAL,
    CONF_AUTH_MODE,
    CONF_AUTO_DISCOVER_CLIENT_TRACKERS,
    CONF_AUTO_DISCOVERY_EXCLUDE_GUESTS,
    CONF_AUTO_DISCOVERY_EXCLUDE_LOCAL_MACS,
    CONF_AUTO_DISCOVERY_EXCLUDED_CLIENTS,
    CONF_AUTO_DISCOVERY_INCLUDE_WIRED,
    CONF_AUTO_DISCOVERY_REQUIRE_NAME,
    CONF_AUTO_DISCOVERY_RETENTION_DAYS,
    CONF_AUTO_DISCOVERY_SIGNAL_ATTRIBUTES,
    CONF_AUTO_DISCOVERY_SSIDS,
    CONF_CLIENT_ID,
    CONF_CLIENT_SCAN_INTERVAL,
    CONF_CLIENT_SECRET,
    CONF_CONTROLLER_TYPE,
    CONF_DEVICE_SCAN_INTERVAL,
    CONF_DISCONNECT_TIMEOUT,
    CONF_ENABLE_CLIENT_BANDWIDTH_SENSORS,
    CONF_ENABLE_CLIENT_BLOCK_SWITCH,
    CONF_ENABLE_CLIENT_RECONNECT_BUTTON,
    CONF_ENABLE_CLIENT_SIGNAL_SENSORS,
    CONF_ENABLE_DEVICE_BANDWIDTH_SENSORS,
    CONF_ENABLE_DEVICE_CLIENT_COUNT_SENSORS,
    CONF_ENABLE_DEVICE_DIAGNOSTIC_SENSORS,
    CONF_ENABLE_DEVICE_RADIO_UTILIZATION_SENSORS,
    CONF_ENABLE_THREAT_HEATMAP_SENSORS,
    CONF_ENABLE_VPN_SENSORS,
    CONF_ENABLE_WAN_SPEED_TEST,
    CONF_OMADA_ID,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_REGION,
    CONF_SELECTED_APPLICATIONS,
    CONF_SELECTED_CLIENTS,
    CONF_SELECTED_SITES,
    CONF_SSID_FILTER,
    CONF_TOKEN_EXPIRES_AT,
    CONF_USERNAME,
    CONTROLLER_TYPE_CLOUD,
    CONTROLLER_TYPE_FUSION,
    CONTROLLER_TYPE_LOCAL,
    DEFAULT_APP_SCAN_INTERVAL,
    DEFAULT_AUTO_DISCOVERY_EXCLUDE_LOCAL_MACS,
    DEFAULT_AUTO_DISCOVERY_RETENTION_DAYS,
    DEFAULT_CLIENT_SCAN_INTERVAL,
    DEFAULT_DEVICE_SCAN_INTERVAL,
    DEFAULT_DISCONNECT_TIMEOUT,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    REGIONS,
    resolve_verify_ssl,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def _classify_connection_error(err: aiohttp.ClientError) -> str:
    """Classify an aiohttp connection error into a specific error key.

    Returns the most specific error key for the given exception.
    """
    try:
        error_message = str(err).lower()
    except Exception:
        error_message = repr(err).lower()

    os_error = err.__cause__ or err.__context__
    try:
        os_message = str(os_error).lower() if os_error else ""
    except Exception:
        os_message = repr(os_error).lower() if os_error else ""

    combined = f"{error_message} {os_message}"

    # Prefer the typed aiohttp certificate error; fall back to matching the
    # certificate wording for wrapped/plainly-constructed ClientError instances.
    if isinstance(err, aiohttp.ClientConnectorCertificateError) or (
        "certificate verify failed" in combined or "self-signed" in combined
    ):
        return "certificate_verify_failed"

    if (
        "name or service not known" in combined
        or "getaddrinfo failed" in combined
        or "nodename nor servname" in combined
    ):
        return "cannot_resolve_host"

    if "connection refused" in combined or "connect call failed" in combined:
        return "connection_refused"

    return "cannot_connect"


# Omada error -7131 ("Controller ID not exist") means the Omada ID can never
# resolve via cloud OpenAPI — Omada Cloud/Central Essentials (the free tier)
# doesn't support Open API at all, confirmed by TP-Link support. Re-checking
# the Omada ID will not help, so this gets a dedicated, actionable message
# instead of the generic "check your credentials" invalid_auth string.
_CONTROLLER_ID_NOT_FOUND_ERROR_CODE = -7131


def _api_error_key(err: OmadaApiError) -> str:
    """Map an API or authentication error to the most specific form error key.

    Connection problems are classified by the aiohttp error the API layer
    wrapped. An HTTP error other than 401 means the controller could not
    answer; everything else (rejected credentials or token, an Omada error
    code) means the credentials were not accepted.
    """
    cause = err.__cause__
    if isinstance(cause, TimeoutError):
        return "timeout"
    if isinstance(cause, aiohttp.ClientError):
        return _classify_connection_error(cause)
    if err.error_code == _CONTROLLER_ID_NOT_FOUND_ERROR_CODE:
        return "controller_id_not_found_free_tier"
    if err.http_status is not None and err.http_status != 401:
        return "cannot_connect"
    return "invalid_auth"


def extract_ssids_from_clients(clients: list[dict[str, Any]]) -> list[str]:
    """Extract unique, sorted SSIDs from a list of client dicts.

    Args:
        clients: List of client dicts from the API (each may have an "ssid" field).

    Returns:
        Sorted list of unique SSID names found in the client list.

    """
    return sorted({c["ssid"] for c in clients if c.get("wireless") and c.get("ssid")})


def filter_clients_by_ssids(
    clients: list[dict[str, Any]], ssid_filter: list[str]
) -> list[dict[str, Any]]:
    """Filter clients to those matching the selected SSIDs.

    Wired clients are always included regardless of the SSID filter.
    When ssid_filter is empty, all clients are returned.

    Args:
        clients: Full list of client dicts.
        ssid_filter: List of SSID names to include. Empty = no filtering.

    Returns:
        Filtered list of clients, online clients first.

    """
    if ssid_filter:
        filter_set = set(ssid_filter)
        clients = [
            c for c in clients if not c.get("wireless") or c.get("ssid") in filter_set
        ]
    return sorted(clients, key=lambda c: not c.get("active"))


async def _discard_tokens(*_args: str) -> None:
    """Accept token updates that need no persistence (Fusion web sessions)."""


class _OmadaFlowApiMixin:
    """Controller access shared by the config flow and the options flow.

    Every request goes through an OmadaApiClient, so the flows use the same
    authentication, pagination and endpoint fallbacks as the coordinators.
    """

    hass: HomeAssistant
    _api_client: OmadaApiClient | None = None
    _fusion_session: aiohttp.ClientSession | None = None

    def _get_fusion_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session with unsafe cookie jar for Fusion.

        Fusion gateways are accessed by IP address, requiring unsafe=True
        on the cookie jar to persist session cookies.
        """
        if self._fusion_session is None:
            self._fusion_session = async_create_clientsession(
                self.hass,
                verify_ssl=False,
                cookie_jar=aiohttp.CookieJar(unsafe=True),
            )
        return self._fusion_session

    @callback
    def async_remove(self) -> None:
        """Release the flow's own Fusion session when the flow ends.

        Sessions from async_create_clientsession must be detached, not closed.
        """
        if self._fusion_session is not None:
            self._fusion_session.detach()

    @property
    def _client(self) -> OmadaApiClient:
        """Return the flow's API client.

        Raises:
            RuntimeError: If no step has set up the client yet

        """
        if self._api_client is None:
            raise RuntimeError("The flow has no API client yet")
        return self._api_client

    async def _get_sites(self) -> list[dict[str, Any]]:
        """Fetch every site of the controller.

        Raises:
            OmadaApiError: If the request fails

        """
        return await self._client.get_sites()

    async def _get_clients(self, site_id: str) -> list[dict[str, Any]]:
        """Fetch every known client of a site, online and offline.

        scope=0 is intentional: the flows must offer offline clients too so
        the user can choose which ones to track. Polling coordinators use
        scope=1 (online only) to avoid controller-side wifiMode warnings.

        Returns:
            List of client dictionaries, or an empty list if the controller
            has no clients endpoint

        Raises:
            OmadaApiError: If the request fails

        """
        try:
            return await self._client.get_all_clients(site_id, scope=0)
        except OmadaApiError as err:
            if err.http_status != 404:
                raise
        _LOGGER.warning(
            "Clients endpoint not supported for site %s; skipping client selection",
            site_id,
        )
        return []

    async def _get_applications(self, site_id: str) -> list[dict[str, Any]]:
        """Fetch every application available for DPI tracking in a site.

        Returns:
            List of application dictionaries, or an empty list if the
            controller does not support application control (HTTP 404 or an
            Omada error code)

        Raises:
            OmadaApiError: If the request fails otherwise

        """
        try:
            return await self._client.get_applications(site_id)
        except OmadaApiError as err:
            if err.http_status != 404 and err.error_code is None:
                raise
            _LOGGER.warning(
                "Applications not available for site %s (%s); "
                "skipping application selection",
                site_id,
                err,
            )
        return []


class OmadaConfigFlow(_OmadaFlowApiMixin, ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Omada Open API."""

    VERSION = 1
    MINOR_VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Get the options flow for this handler."""
        return OmadaOptionsFlowHandler(config_entry)

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._controller_type: str | None = None
        self._region: str | None = None
        self._api_url: str | None = None
        self._omada_id: str | None = None
        self._client_id: str | None = None
        self._client_secret: str | None = None
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expires_at: dt.datetime | None = None
        self._available_sites: list[dict[str, Any]] = []
        self._selected_site_ids: list[str] = []
        self._available_clients: list[dict[str, Any]] = []
        self._selected_client_macs: list[str] = []
        self._available_applications: list[dict[str, Any]] = []
        self._ssid_filter: list[str] = []
        # Default False matches entries created before verify_ssl existed,
        # restoring pre-v1.10 connectivity for self-signed controllers.
        self._verify_ssl: bool = False
        # Fusion-specific
        self._fusion_username: str | None = None
        self._fusion_password: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step where user selects controller type."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._controller_type = user_input[CONF_CONTROLLER_TYPE]

            if self._controller_type == CONTROLLER_TYPE_CLOUD:
                return await self.async_step_cloud()
            if self._controller_type == CONTROLLER_TYPE_FUSION:
                return await self.async_step_fusion()
            return await self.async_step_local()

        # Create schema for controller type selection
        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_CONTROLLER_TYPE, default=CONTROLLER_TYPE_LOCAL
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            CONTROLLER_TYPE_LOCAL,
                            CONTROLLER_TYPE_CLOUD,
                            CONTROLLER_TYPE_FUSION,
                        ],
                        translation_key="controller_type",
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,  # type: ignore[arg-type]
            errors=errors,
        )

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle cloud controller region selection."""
        errors: dict[str, str] = {}

        # TP-Link cloud endpoints present valid certificates.
        self._verify_ssl = True

        if user_input is not None:
            self._region = user_input[CONF_REGION]
            self._api_url = REGIONS[self._region]["api_url"]
            return await self.async_step_credentials()

        # Create schema for region selection
        data_schema = vol.Schema(
            {
                vol.Required(CONF_REGION): SelectSelector(
                    SelectSelectorConfig(
                        options=list(REGIONS),
                        translation_key="region",
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="cloud",
            data_schema=data_schema,  # type: ignore[arg-type]
            errors=errors,
        )

    async def async_step_local(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle local controller URL input."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._api_url = user_input[CONF_API_URL].rstrip("/")
            self._verify_ssl = user_input[CONF_VERIFY_SSL]
            # Validate URL format
            if not self._api_url.startswith(("http://", "https://")):
                errors[CONF_API_URL] = "invalid_url"
            else:
                return await self.async_step_credentials()

        # Create schema for URL input
        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_API_URL,
                    description={"suggested_value": "https://"},
                ): cv.string,
                vol.Required(CONF_VERIFY_SSL, default=True): cv.boolean,
            }
        )

        return self.async_show_form(
            step_id="local",
            data_schema=data_schema,  # type: ignore[arg-type]
            errors=errors,
            description_placeholders={
                "example_url": "https://192.168.1.100:8043",
            },
        )

    async def async_step_fusion(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle Fusion Gateway credentials input."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_url = user_input[CONF_API_URL].rstrip("/")
            if not api_url.startswith(("http://", "https://")):
                errors[CONF_API_URL] = "invalid_url"
            else:
                username = user_input[CONF_USERNAME]
                password = user_input[CONF_PASSWORD]

                try:
                    session = self._get_fusion_session()
                    # Auto-detect Omada CID
                    omada_id = await async_get_controller_id(session, api_url)

                    # Validate credentials via web login. The client below
                    # reuses this session for every later step.
                    auth = WebSessionAuth(
                        session=session,
                        token_update_callback=_discard_tokens,
                        api_url=api_url,
                        omada_id=omada_id,
                        username=username,
                        password=password,
                    )
                    await auth.authenticate()

                    # Store for later steps
                    self._api_url = api_url
                    self._omada_id = omada_id
                    self._controller_type = CONTROLLER_TYPE_FUSION
                    self._fusion_username = username
                    self._fusion_password = password
                    self._api_client = OmadaApiClient.from_auth(
                        session, auth, api_url, omada_id
                    )

                    # Prevent duplicate entries
                    await self.async_set_unique_id(f"fusion_{omada_id}")
                    self._abort_if_unique_id_configured()

                    sites = await self._get_sites()
                    if not sites:
                        errors["base"] = "no_sites"
                    else:
                        self._available_sites = sites
                        # Auto-select if single site
                        if len(sites) == 1:
                            self._selected_site_ids = [sites[0]["siteId"]]
                            return await self.async_step_ssid_filter()
                        return await self.async_step_sites()

                except AbortFlow:
                    # The duplicate check aborts the flow; it is no login error.
                    raise
                except TimeoutError:
                    errors["base"] = "timeout"
                except OmadaApiError as err:
                    errors["base"] = _api_error_key(err)
                    _LOGGER.warning(
                        "Fusion gateway check failed (%s): %s", errors["base"], err
                    )
                except Exception:
                    _LOGGER.exception("Unexpected error during Fusion login")
                    errors["base"] = "unknown"

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_API_URL,
                    description={"suggested_value": "https://"},
                ): cv.string,
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
            }
        )

        return self.async_show_form(
            step_id="fusion",
            data_schema=data_schema,  # type: ignore[arg-type]
            errors=errors,
            description_placeholders={
                "example_url": "https://192.168.1.1",
            },
        )

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle credentials input step."""
        _LOGGER.debug(
            "async_step_credentials called with user_input: %s", user_input is not None
        )
        errors: dict[str, str] = {}

        if user_input is not None:
            self._omada_id = user_input[CONF_OMADA_ID]
            self._client_id = user_input[CONF_CLIENT_ID]
            self._client_secret = user_input[CONF_CLIENT_SECRET]

            # Prevent duplicate config entries for the same controller
            await self.async_set_unique_id(self._omada_id)
            self._abort_if_unique_id_configured()

            # The cloud or local step sets the URL; restart if it is missing.
            if self._api_url is None:
                return await self.async_step_user()
            # Validate credentials by obtaining access token
            try:
                await self._authenticate(
                    self._api_url,
                    self._omada_id,
                    self._client_id,
                    self._client_secret,
                )

                # Fetch available sites
                sites = await self._get_sites()
                if not sites:
                    errors["base"] = "no_sites"
                else:
                    self._available_sites = sites
                    return await self.async_step_sites()

            except TimeoutError:
                _LOGGER.warning("Connection timed out to %s", self._api_url)
                errors["base"] = "timeout"
            except OmadaApiError as err:
                errors["base"] = _api_error_key(err)
                _LOGGER.warning(
                    "Credential check failed for %s (%s): %s",
                    self._api_url,
                    errors["base"],
                    err,
                )
            except Exception:
                _LOGGER.exception("Unexpected exception during authentication")
                errors["base"] = "unknown"

        # Create schema for credentials input
        data_schema = vol.Schema(
            {
                vol.Required(CONF_OMADA_ID): cv.string,
                vol.Required(CONF_CLIENT_ID): cv.string,
                vol.Required(CONF_CLIENT_SECRET): cv.string,
            }
        )

        description_placeholders = {}
        if self._controller_type == CONTROLLER_TYPE_CLOUD and self._region:
            description_placeholders["controller_info"] = (
                f"Region: {REGIONS[self._region]['name']}"
            )
        else:
            description_placeholders["controller_info"] = f"URL: {self._api_url}"

        return self.async_show_form(
            step_id="credentials",
            data_schema=data_schema,  # type: ignore[arg-type]
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_sites(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle site selection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._selected_site_ids = user_input[CONF_SELECTED_SITES]

            # Proceed to SSID filter (which then proceeds to client selection)
            return await self.async_step_ssid_filter()

        # Create site selection options
        site_options = [
            SelectOptionDict(
                value=site["siteId"],
                label=f"{site['name']} ({site.get('region', 'Unknown')})",
            )
            for site in self._available_sites
        ]

        data_schema = vol.Schema(
            {
                vol.Required(CONF_SELECTED_SITES): SelectSelector(
                    SelectSelectorConfig(
                        options=site_options,
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="sites",
            data_schema=data_schema,  # type: ignore[arg-type]
            errors=errors,
            description_placeholders={
                "site_count": str(len(self._available_sites)),
            },
        )

    def _generate_entry_data(self) -> dict[str, Any]:
        """Generate config entry data dict based on controller type."""
        if self._controller_type == CONTROLLER_TYPE_FUSION:
            return {
                CONF_CONTROLLER_TYPE: self._controller_type,
                CONF_AUTH_MODE: AUTH_MODE_WEB_SESSION,
                CONF_API_URL: self._api_url,
                CONF_OMADA_ID: self._omada_id,
                CONF_USERNAME: self._fusion_username,
                CONF_PASSWORD: self._fusion_password,
                CONF_SELECTED_SITES: self._selected_site_ids,
            }
        return {
            CONF_CONTROLLER_TYPE: self._controller_type,
            CONF_AUTH_MODE: AUTH_MODE_OPENAPI,
            CONF_API_URL: self._api_url,
            CONF_OMADA_ID: self._omada_id,
            CONF_CLIENT_ID: self._client_id,
            CONF_CLIENT_SECRET: self._client_secret,
            CONF_ACCESS_TOKEN: self._access_token,
            CONF_REFRESH_TOKEN: self._refresh_token,
            CONF_TOKEN_EXPIRES_AT: self._token_expires_at_iso(),
            CONF_SELECTED_SITES: self._selected_site_ids,
            CONF_VERIFY_SSL: self._verify_ssl,
        }

    def _generate_entry_title(self) -> str:
        """Generate config entry title from selected sites."""
        if self._selected_site_ids:
            first_site = next(
                site
                for site in self._available_sites
                if site["siteId"] in self._selected_site_ids
            )
            title = f"Omada - {first_site['name']}"
            if len(self._selected_site_ids) > 1:
                title += f" (+{len(self._selected_site_ids) - 1})"
            return title
        return "Omada Controller"

    async def async_step_ssid_filter(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle optional SSID filter step before client selection.

        Shows available SSIDs extracted from the client list.
        User can select SSIDs to pre-filter the client list, or leave
        the field empty to show all clients.
        """
        if user_input is not None:
            self._ssid_filter = user_input.get(CONF_SSID_FILTER, [])
            return await self.async_step_clients()

        # Fetch clients to extract SSIDs
        all_clients: list[dict[str, Any]] = []
        try:
            for site_id in self._selected_site_ids:
                clients_data = await self._get_clients(site_id)
                all_clients.extend(clients_data)
            self._available_clients = all_clients
        except Exception:
            _LOGGER.exception("Failed to fetch clients for SSID extraction")
            # Skip SSID filter step on error
            return await self.async_step_clients()

        available_ssids = extract_ssids_from_clients(all_clients)

        if not available_ssids:
            # No wireless clients — skip SSID filter step
            return await self.async_step_clients()

        ssid_options = [
            SelectOptionDict(value=ssid, label=ssid) for ssid in available_ssids
        ]

        data_schema = vol.Schema(
            {
                vol.Optional(CONF_SSID_FILTER, default=[]): SelectSelector(
                    SelectSelectorConfig(
                        options=ssid_options,
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="ssid_filter",
            data_schema=data_schema,  # type: ignore[arg-type]
            description_placeholders={
                "ssid_count": str(len(available_ssids)),
                "client_count": str(len(all_clients)),
            },
        )

    async def async_step_clients(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle client selection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._selected_client_macs = user_input.get(CONF_SELECTED_CLIENTS, [])

            # Proceed to application selection
            return await self.async_step_applications()

        # Fetch all clients only if not already loaded (e.g. by ssid_filter step)
        if not self._available_clients:
            try:
                all_clients = []
                for site_id in self._selected_site_ids:
                    clients_data = await self._get_clients(site_id)
                    all_clients.extend(clients_data)

                self._available_clients = all_clients
            except Exception:
                _LOGGER.exception("Failed to fetch clients")
                errors["base"] = "cannot_connect"

        if not self._available_clients:
            # No clients available, skip client selection
            title = self._generate_entry_title()

            return self.async_create_entry(
                title=title,
                data=self._generate_entry_data(),
                options={
                    CONF_SELECTED_CLIENTS: [],
                    CONF_SELECTED_APPLICATIONS: [],
                },
            )

        # Apply SSID filter to the displayed client list
        display_clients = filter_clients_by_ssids(
            self._available_clients, self._ssid_filter
        )

        # Create client selection options
        client_options = []
        for client in display_clients:
            name = client.get("name") or client.get("hostName") or "Unknown"
            mac = client.get("mac", "")
            ip = client.get("ip", "N/A")
            online = "🟢" if client.get("active") else "🔴"

            client_options.append(
                SelectOptionDict(
                    value=mac,
                    label=f"{online} {name} - {ip} ({mac})",
                )
            )

        data_schema = vol.Schema(
            {
                vol.Optional(CONF_SELECTED_CLIENTS, default=[]): SelectSelector(
                    SelectSelectorConfig(
                        options=client_options,
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="clients",
            data_schema=data_schema,  # type: ignore[arg-type]
            errors=errors,
            description_placeholders={
                "client_count": str(len(display_clients)),
            },
        )

    async def _authenticate(
        self, api_url: str, omada_id: str, client_id: str, client_secret: str
    ) -> None:
        """Validate OAuth client credentials and keep a client for later steps.

        Obtains tokens with the client_credentials grant. The tokens reach the
        flow through _async_store_tokens, also when the client refreshes them
        in a later step.

        Raises:
            OmadaApiError: If the controller rejects the credentials or
                cannot be reached

        """
        session = async_get_clientsession(self.hass, verify_ssl=self._verify_ssl)
        auth = ClientCredentialsAuth(
            session=session,
            token_update_callback=self._async_store_tokens,
            api_url=api_url,
            omada_id=omada_id,
            client_id=client_id,
            client_secret=client_secret,
            access_token="",
            refresh_token="",
            token_expires_at=dt.datetime.now(dt.UTC),
        )
        await auth.authenticate()
        self._api_client = OmadaApiClient.from_auth(session, auth, api_url, omada_id)

    async def _async_store_tokens(
        self, access_token: str, refresh_token: str, expires_at_iso: str
    ) -> None:
        """Keep the latest OAuth tokens for the entry this flow creates."""
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._token_expires_at = dt.datetime.fromisoformat(expires_at_iso)

    def _token_expires_at_iso(self) -> str:
        """Return the token expiry as stored in the entry data."""
        return self._token_expires_at.isoformat() if self._token_expires_at else ""

    async def async_step_applications(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle application selection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_app_ids = user_input.get(CONF_SELECTED_APPLICATIONS, [])

            title = self._generate_entry_title()

            # Create config entry
            return self.async_create_entry(
                title=title,
                data=self._generate_entry_data(),
                options={
                    CONF_SELECTED_CLIENTS: self._selected_client_macs,
                    CONF_SELECTED_APPLICATIONS: selected_app_ids,
                },
            )

        # Fetch applications from the first selected site
        try:
            if self._selected_site_ids:
                first_site_id = self._selected_site_ids[0]
                self._available_applications = await self._get_applications(
                    first_site_id
                )
        except Exception:
            _LOGGER.exception("Failed to fetch applications")
            errors["base"] = "cannot_connect"

        if not self._available_applications:
            # No applications available or DPI not supported, skip and create entry
            title = self._generate_entry_title()

            return self.async_create_entry(
                title=title,
                data=self._generate_entry_data(),
                options={
                    CONF_SELECTED_CLIENTS: self._selected_client_macs,
                    CONF_SELECTED_APPLICATIONS: [],
                },
            )

        # Create application selection options (sorted by family then name)
        app_options = []
        for app in sorted(
            self._available_applications,
            key=lambda x: (x.get("family", ""), x.get("application", "")),
        ):
            app_id = str(app.get("applicationId", ""))
            app_name = app.get("application", "Unknown")
            family = app.get("family", "Other")

            app_options.append(
                SelectOptionDict(
                    value=app_id,
                    label=f"{app_name} ({family})",
                )
            )

        data_schema = vol.Schema(
            {
                vol.Optional(CONF_SELECTED_APPLICATIONS, default=[]): SelectSelector(
                    SelectSelectorConfig(
                        options=app_options,
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="applications",
            data_schema=data_schema,  # type: ignore[arg-type]
            errors=errors,
            description_placeholders={
                "app_count": str(len(self._available_applications)),
            },
        )

    # ------------------------------------------------------------------
    # Reconfigure flow
    # ------------------------------------------------------------------

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of the integration."""
        errors: dict[str, str] = {}
        reconfigure_entry = self._get_reconfigure_entry()

        if user_input is not None:
            controller_type = user_input.get(
                CONF_CONTROLLER_TYPE,
                reconfigure_entry.data.get(CONF_CONTROLLER_TYPE, CONTROLLER_TYPE_CLOUD),
            )
            self._controller_type = controller_type

            if controller_type == CONTROLLER_TYPE_CLOUD:
                region = user_input.get(
                    CONF_REGION,
                    reconfigure_entry.data.get(CONF_REGION, "us"),
                )
                self._region = region
                self._api_url = REGIONS[region]["api_url"]
            else:
                api_url = user_input.get(
                    CONF_API_URL,
                    reconfigure_entry.data.get(CONF_API_URL, ""),
                )
                if not api_url or not api_url.startswith(("http://", "https://")):
                    errors["base"] = "invalid_url"
                    return self._show_reconfigure_form(reconfigure_entry, errors)
                self._api_url = api_url.rstrip("/")

            omada_id = user_input.get(
                CONF_OMADA_ID,
                reconfigure_entry.data.get(CONF_OMADA_ID, ""),
            )
            client_id = user_input.get(
                CONF_CLIENT_ID,
                reconfigure_entry.data.get(CONF_CLIENT_ID, ""),
            )
            client_secret = user_input.get(
                CONF_CLIENT_SECRET,
                reconfigure_entry.data.get(CONF_CLIENT_SECRET, ""),
            )

            self._omada_id = omada_id
            self._client_id = client_id
            self._client_secret = client_secret
            self._verify_ssl = resolve_verify_ssl(
                controller_type,
                user_input.get(
                    CONF_VERIFY_SSL,
                    reconfigure_entry.data.get(CONF_VERIFY_SSL),
                ),
            )

            try:
                await self._authenticate(
                    self._api_url,
                    omada_id,
                    client_id,
                    client_secret,
                )
            except TimeoutError:
                _LOGGER.warning("Connection timed out to %s", self._api_url)
                errors["base"] = "timeout"
                return self._show_reconfigure_form(reconfigure_entry, errors)
            except OmadaApiError as err:
                errors["base"] = _api_error_key(err)
                _LOGGER.warning(
                    "Credential check failed during reconfigure (%s): %s",
                    errors["base"],
                    err,
                )
                return self._show_reconfigure_form(reconfigure_entry, errors)
            except Exception:
                _LOGGER.exception("Unexpected exception during reconfigure")
                errors["base"] = "unknown"
                return self._show_reconfigure_form(reconfigure_entry, errors)

            # Proceed to site selection
            return await self.async_step_reconfigure_sites()

        return self._show_reconfigure_form(reconfigure_entry, errors)

    def _show_reconfigure_form(
        self,
        entry: ConfigEntry,
        errors: dict[str, str],
    ) -> ConfigFlowResult:
        """Show the reconfigure form with current values pre-populated."""
        controller_type = entry.data.get(CONF_CONTROLLER_TYPE, CONTROLLER_TYPE_CLOUD)
        is_cloud = controller_type == CONTROLLER_TYPE_CLOUD

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_CONTROLLER_TYPE,
                    default=controller_type,
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[CONTROLLER_TYPE_CLOUD, CONTROLLER_TYPE_LOCAL],
                        translation_key="controller_type",
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional(
                    CONF_REGION,
                    default=entry.data.get(CONF_REGION, "us"),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=list(REGIONS),
                        translation_key="region",
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional(
                    CONF_API_URL,
                    default=entry.data.get(CONF_API_URL, "") if not is_cloud else "",
                ): cv.string,
                vol.Required(
                    CONF_OMADA_ID,
                    default=entry.data.get(CONF_OMADA_ID, ""),
                ): cv.string,
                vol.Required(
                    CONF_CLIENT_ID,
                    default=entry.data.get(CONF_CLIENT_ID, ""),
                ): cv.string,
                vol.Required(CONF_CLIENT_SECRET): cv.string,
            }
        )
        # Cloud controllers always verify TLS, so the toggle would be
        # misleading; only local controllers may opt out.
        if not is_cloud:
            data_schema = data_schema.extend(
                {
                    vol.Optional(
                        CONF_VERIFY_SSL,
                        default=entry.data.get(CONF_VERIFY_SSL, False),
                    ): cv.boolean,
                }
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=data_schema,  # type: ignore[arg-type]
            errors=errors,
        )

    async def async_step_reconfigure_sites(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle site selection during reconfiguration."""
        reconfigure_entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            selected = user_input.get(CONF_SELECTED_SITES, [])
            if not selected:
                errors["base"] = "no_sites"
            else:
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    data_updates={
                        CONF_CONTROLLER_TYPE: self._controller_type,
                        CONF_REGION: self._region,
                        CONF_API_URL: self._api_url,
                        CONF_OMADA_ID: self._omada_id,
                        CONF_CLIENT_ID: self._client_id,
                        CONF_CLIENT_SECRET: self._client_secret,
                        CONF_ACCESS_TOKEN: self._access_token,
                        CONF_REFRESH_TOKEN: self._refresh_token,
                        CONF_TOKEN_EXPIRES_AT: self._token_expires_at_iso(),
                        CONF_SELECTED_SITES: selected,
                        CONF_VERIFY_SSL: self._verify_ssl,
                    },
                )

        # Fetch available sites
        try:
            sites = await self._get_sites()
        except Exception:
            _LOGGER.exception("Failed to fetch sites during reconfigure")
            return self.async_abort(reason="cannot_connect")

        if not sites:
            return self.async_abort(reason="no_sites")

        site_options = {
            site["siteId"]: site.get("name", site["siteId"]) for site in sites
        }
        previously_selected = reconfigure_entry.data.get(CONF_SELECTED_SITES, [])
        # Only default to previously selected sites that still exist.
        default_selected = [s for s in previously_selected if s in site_options]

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_SELECTED_SITES,
                    default=default_selected,
                ): cv.multi_select(site_options),
            }
        )

        return self.async_show_form(
            step_id="reconfigure_sites",
            data_schema=data_schema,  # type: ignore[arg-type]
            errors=errors,
            description_placeholders={
                "site_count": str(len(sites)),
            },
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reauth upon authentication expiration.

        Args:
            entry_data: The config entry data

        Returns:
            ConfigFlowResult to show reauth confirmation

        """
        _LOGGER.debug("Reauth flow started")
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reauth confirmation and credentials update.

        Args:
            user_input: User input from the form

        Returns:
            ConfigFlowResult to update entry or show form again

        """
        _LOGGER.debug("Reauth confirmation submitted: %s", user_input is not None)
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        # Validation must match the entry's effective setting; reauth does
        # not change it.
        self._verify_ssl = resolve_verify_ssl(
            reauth_entry.data.get(CONF_CONTROLLER_TYPE),
            reauth_entry.data.get(CONF_VERIFY_SSL),
        )
        _LOGGER.debug("Reauth entry retrieved: %s", reauth_entry.title)

        if user_input is not None:
            # Use existing config entry data for non-credential fields
            api_url = reauth_entry.data[CONF_API_URL]
            omada_id = user_input.get(CONF_OMADA_ID, reauth_entry.data[CONF_OMADA_ID])
            client_id = user_input[CONF_CLIENT_ID]
            client_secret = user_input[CONF_CLIENT_SECRET]

            try:
                # Get new tokens
                await self._authenticate(api_url, omada_id, client_id, client_secret)

                # Update config entry with new credentials
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={
                        CONF_CLIENT_ID: client_id,
                        CONF_CLIENT_SECRET: client_secret,
                        CONF_OMADA_ID: omada_id,
                        CONF_ACCESS_TOKEN: self._access_token,
                        CONF_REFRESH_TOKEN: self._refresh_token,
                        CONF_TOKEN_EXPIRES_AT: self._token_expires_at_iso(),
                    },
                )

            except TimeoutError:
                _LOGGER.warning("Connection timed out during reauth")
                errors["base"] = "timeout"
            except OmadaApiError as err:
                errors["base"] = _api_error_key(err)
                _LOGGER.warning(
                    "Credential check failed during reauth (%s): %s",
                    errors["base"],
                    err,
                )
            except Exception:
                _LOGGER.exception("Unexpected exception during reauth")
                errors["base"] = "unknown"

        # Show reauth form
        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_OMADA_ID,
                    default=reauth_entry.data.get(CONF_OMADA_ID),
                ): cv.string,
                vol.Required(CONF_CLIENT_ID): cv.string,
                vol.Required(CONF_CLIENT_SECRET): cv.string,
            }
        )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=data_schema,  # type: ignore[arg-type]
            errors=errors,
        )


class OmadaOptionsFlowHandler(_OmadaFlowApiMixin, OptionsFlow):
    """Handle options flow for Omada Open API."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__()
        self._selected_site_ids: list[str] = []
        self._available_clients: list[dict[str, Any]] = []
        self._available_applications: list[dict[str, Any]] = []
        self._ssid_filter: list[str] = []
        # Working client selection, tracked across SSID filter changes so
        # narrowing the visible list doesn't invalidate (or drop) selections
        # belonging to currently-hidden SSIDs. None until first initialized
        # from the persisted entry options.
        self._working_client_macs: list[str] | None = None

    def _ensure_api_client(self) -> None:
        """Set up the API client for the entry, reusing the running one.

        Fusion gateways allow only one active session: an independent login
        would invalidate the coordinators' session (and the other way round),
        and some Fusion endpoints check the session cookie together with the
        CSRF token. A loaded entry's client is therefore reused. Only an entry
        that is not loaded gets its own client, built from the entry data;
        OAuth tokens it refreshes are written back to the entry.
        """
        if self._api_client is not None:
            return
        runtime_data = getattr(self.config_entry, "runtime_data", None)
        if runtime_data is not None:
            self._api_client = runtime_data.api_client
            return

        data = self.config_entry.data
        api_url: str = data[CONF_API_URL]
        omada_id: str = data[CONF_OMADA_ID]
        auth_mode = data.get(
            CONF_AUTH_MODE,
            AUTH_MODE_WEB_SESSION if CONF_USERNAME in data else AUTH_MODE_OPENAPI,
        )
        session: aiohttp.ClientSession
        auth: OmadaAuthStrategy
        if auth_mode == AUTH_MODE_WEB_SESSION:
            session = self._get_fusion_session()
            auth = WebSessionAuth(
                session=session,
                token_update_callback=_discard_tokens,
                api_url=api_url,
                omada_id=omada_id,
                username=data[CONF_USERNAME],
                password=data[CONF_PASSWORD],
            )
        else:
            session = async_get_clientsession(
                self.hass,
                verify_ssl=resolve_verify_ssl(
                    data.get(CONF_CONTROLLER_TYPE), data.get(CONF_VERIFY_SSL)
                ),
            )
            auth = ClientCredentialsAuth(
                session=session,
                token_update_callback=self._async_persist_tokens,
                api_url=api_url,
                omada_id=omada_id,
                client_id=data[CONF_CLIENT_ID],
                client_secret=data[CONF_CLIENT_SECRET],
                access_token=data[CONF_ACCESS_TOKEN],
                refresh_token=data[CONF_REFRESH_TOKEN],
                token_expires_at=dt.datetime.fromisoformat(data[CONF_TOKEN_EXPIRES_AT]),
            )
        self._api_client = OmadaApiClient.from_auth(session, auth, api_url, omada_id)

    async def _async_persist_tokens(
        self, access_token: str, refresh_token: str, expires_at_iso: str
    ) -> None:
        """Write OAuth tokens refreshed by the flow's own client to the entry."""
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={
                **self.config_entry.data,
                CONF_ACCESS_TOKEN: access_token,
                CONF_REFRESH_TOKEN: refresh_token,
                CONF_TOKEN_EXPIRES_AT: expires_at_iso,
            },
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options - show menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "client_selection",
                "application_selection",
                "update_intervals",
                "tracker_settings",
                "device_entity_settings",
                "client_entity_settings",
                "site_entity_settings",
                "gateway_entity_settings",
            ],
        )

    async def async_step_gateway_entity_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle gateway VPN and WAN speed-test entity toggles."""
        opts = self.config_entry.options

        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    **opts,
                    CONF_ENABLE_VPN_SENSORS: user_input.get(
                        CONF_ENABLE_VPN_SENSORS, True
                    ),
                    CONF_ENABLE_WAN_SPEED_TEST: user_input.get(
                        CONF_ENABLE_WAN_SPEED_TEST, True
                    ),
                },
            )

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_ENABLE_VPN_SENSORS,
                    default=opts.get(CONF_ENABLE_VPN_SENSORS, True),
                ): bool,
                vol.Required(
                    CONF_ENABLE_WAN_SPEED_TEST,
                    default=opts.get(CONF_ENABLE_WAN_SPEED_TEST, True),
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="gateway_entity_settings",
            data_schema=data_schema,  # type: ignore[arg-type]
        )

    async def async_step_tracker_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle device tracker and automatic client discovery settings."""
        opts = self.config_entry.options
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    **opts,
                    CONF_DISCONNECT_TIMEOUT: user_input[CONF_DISCONNECT_TIMEOUT],
                    CONF_AUTO_DISCOVER_CLIENT_TRACKERS: user_input.get(
                        CONF_AUTO_DISCOVER_CLIENT_TRACKERS, False
                    ),
                    CONF_AUTO_DISCOVERY_RETENTION_DAYS: user_input.get(
                        CONF_AUTO_DISCOVERY_RETENTION_DAYS,
                        DEFAULT_AUTO_DISCOVERY_RETENTION_DAYS,
                    ),
                    CONF_AUTO_DISCOVERY_SSIDS: list(
                        user_input.get(CONF_AUTO_DISCOVERY_SSIDS, [])
                    ),
                    CONF_AUTO_DISCOVERY_INCLUDE_WIRED: user_input.get(
                        CONF_AUTO_DISCOVERY_INCLUDE_WIRED, True
                    ),
                    CONF_AUTO_DISCOVERY_EXCLUDE_GUESTS: user_input.get(
                        CONF_AUTO_DISCOVERY_EXCLUDE_GUESTS, True
                    ),
                    CONF_AUTO_DISCOVERY_EXCLUDE_LOCAL_MACS: user_input.get(
                        CONF_AUTO_DISCOVERY_EXCLUDE_LOCAL_MACS,
                        DEFAULT_AUTO_DISCOVERY_EXCLUDE_LOCAL_MACS,
                    ),
                    CONF_AUTO_DISCOVERY_REQUIRE_NAME: user_input.get(
                        CONF_AUTO_DISCOVERY_REQUIRE_NAME, False
                    ),
                    CONF_AUTO_DISCOVERY_EXCLUDED_CLIENTS: list(
                        user_input.get(CONF_AUTO_DISCOVERY_EXCLUDED_CLIENTS, [])
                    ),
                    CONF_AUTO_DISCOVERY_SIGNAL_ATTRIBUTES: user_input.get(
                        CONF_AUTO_DISCOVERY_SIGNAL_ATTRIBUTES, True
                    ),
                },
            )

        current_timeout = opts.get(CONF_DISCONNECT_TIMEOUT, DEFAULT_DISCONNECT_TIMEOUT)
        saved_ssids = opts.get(CONF_AUTO_DISCOVERY_SSIDS, [])
        if isinstance(saved_ssids, str):
            saved_ssids = [
                ssid.strip() for ssid in saved_ssids.split(",") if ssid.strip()
            ]
        saved_exclusions = opts.get(CONF_AUTO_DISCOVERY_EXCLUDED_CLIENTS, [])

        data_schema = vol.Schema(
            {
                vol.Required(CONF_DISCONNECT_TIMEOUT, default=current_timeout): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=60)
                ),
                vol.Required(
                    CONF_AUTO_DISCOVER_CLIENT_TRACKERS,
                    default=opts.get(CONF_AUTO_DISCOVER_CLIENT_TRACKERS, False),
                ): bool,
                vol.Required(
                    CONF_AUTO_DISCOVERY_RETENTION_DAYS,
                    default=opts.get(
                        CONF_AUTO_DISCOVERY_RETENTION_DAYS,
                        DEFAULT_AUTO_DISCOVERY_RETENTION_DAYS,
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=3650)),
                vol.Optional(
                    CONF_AUTO_DISCOVERY_SSIDS,
                    default=saved_ssids,
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=sorted(set(saved_ssids)),
                        multiple=True,
                        custom_value=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_AUTO_DISCOVERY_INCLUDE_WIRED,
                    default=opts.get(CONF_AUTO_DISCOVERY_INCLUDE_WIRED, True),
                ): bool,
                vol.Required(
                    CONF_AUTO_DISCOVERY_EXCLUDE_GUESTS,
                    default=opts.get(CONF_AUTO_DISCOVERY_EXCLUDE_GUESTS, True),
                ): bool,
                vol.Required(
                    CONF_AUTO_DISCOVERY_EXCLUDE_LOCAL_MACS,
                    default=opts.get(
                        CONF_AUTO_DISCOVERY_EXCLUDE_LOCAL_MACS,
                        DEFAULT_AUTO_DISCOVERY_EXCLUDE_LOCAL_MACS,
                    ),
                ): bool,
                vol.Required(
                    CONF_AUTO_DISCOVERY_REQUIRE_NAME,
                    default=opts.get(CONF_AUTO_DISCOVERY_REQUIRE_NAME, False),
                ): bool,
                vol.Optional(
                    CONF_AUTO_DISCOVERY_EXCLUDED_CLIENTS,
                    default=saved_exclusions,
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=sorted(set(saved_exclusions)),
                        multiple=True,
                        custom_value=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_AUTO_DISCOVERY_SIGNAL_ATTRIBUTES,
                    default=opts.get(CONF_AUTO_DISCOVERY_SIGNAL_ATTRIBUTES, True),
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="tracker_settings",
            data_schema=data_schema,  # type: ignore[arg-type]
        )

    async def async_step_device_entity_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle device entity category toggles."""
        opts = self.config_entry.options

        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    **opts,
                    CONF_ENABLE_DEVICE_BANDWIDTH_SENSORS: user_input.get(
                        CONF_ENABLE_DEVICE_BANDWIDTH_SENSORS, True
                    ),
                    CONF_ENABLE_DEVICE_CLIENT_COUNT_SENSORS: user_input.get(
                        CONF_ENABLE_DEVICE_CLIENT_COUNT_SENSORS, True
                    ),
                    CONF_ENABLE_DEVICE_DIAGNOSTIC_SENSORS: user_input.get(
                        CONF_ENABLE_DEVICE_DIAGNOSTIC_SENSORS, True
                    ),
                    CONF_ENABLE_DEVICE_RADIO_UTILIZATION_SENSORS: user_input.get(
                        CONF_ENABLE_DEVICE_RADIO_UTILIZATION_SENSORS, True
                    ),
                },
            )

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_ENABLE_DEVICE_BANDWIDTH_SENSORS,
                    default=opts.get(CONF_ENABLE_DEVICE_BANDWIDTH_SENSORS, True),
                ): bool,
                vol.Required(
                    CONF_ENABLE_DEVICE_CLIENT_COUNT_SENSORS,
                    default=opts.get(CONF_ENABLE_DEVICE_CLIENT_COUNT_SENSORS, True),
                ): bool,
                vol.Required(
                    CONF_ENABLE_DEVICE_DIAGNOSTIC_SENSORS,
                    default=opts.get(CONF_ENABLE_DEVICE_DIAGNOSTIC_SENSORS, True),
                ): bool,
                vol.Required(
                    CONF_ENABLE_DEVICE_RADIO_UTILIZATION_SENSORS,
                    default=opts.get(
                        CONF_ENABLE_DEVICE_RADIO_UTILIZATION_SENSORS, True
                    ),
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="device_entity_settings",
            data_schema=data_schema,  # type: ignore[arg-type]
        )

    async def async_step_client_entity_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle client entity category toggles."""
        opts = self.config_entry.options

        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    **opts,
                    CONF_ENABLE_CLIENT_BANDWIDTH_SENSORS: user_input.get(
                        CONF_ENABLE_CLIENT_BANDWIDTH_SENSORS, True
                    ),
                    CONF_ENABLE_CLIENT_SIGNAL_SENSORS: user_input.get(
                        CONF_ENABLE_CLIENT_SIGNAL_SENSORS, True
                    ),
                    CONF_ENABLE_CLIENT_BLOCK_SWITCH: user_input.get(
                        CONF_ENABLE_CLIENT_BLOCK_SWITCH, True
                    ),
                    CONF_ENABLE_CLIENT_RECONNECT_BUTTON: user_input.get(
                        CONF_ENABLE_CLIENT_RECONNECT_BUTTON, True
                    ),
                },
            )

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_ENABLE_CLIENT_BANDWIDTH_SENSORS,
                    default=opts.get(CONF_ENABLE_CLIENT_BANDWIDTH_SENSORS, True),
                ): bool,
                vol.Required(
                    CONF_ENABLE_CLIENT_SIGNAL_SENSORS,
                    default=opts.get(CONF_ENABLE_CLIENT_SIGNAL_SENSORS, True),
                ): bool,
                vol.Required(
                    CONF_ENABLE_CLIENT_BLOCK_SWITCH,
                    default=opts.get(CONF_ENABLE_CLIENT_BLOCK_SWITCH, True),
                ): bool,
                vol.Required(
                    CONF_ENABLE_CLIENT_RECONNECT_BUTTON,
                    default=opts.get(CONF_ENABLE_CLIENT_RECONNECT_BUTTON, True),
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="client_entity_settings",
            data_schema=data_schema,  # type: ignore[arg-type]
        )

    async def async_step_site_entity_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle site-level entity toggles (threat heatmap sensors)."""
        opts = self.config_entry.options

        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    **opts,
                    CONF_ENABLE_THREAT_HEATMAP_SENSORS: user_input.get(
                        CONF_ENABLE_THREAT_HEATMAP_SENSORS, True
                    ),
                },
            )

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_ENABLE_THREAT_HEATMAP_SENSORS,
                    default=opts.get(CONF_ENABLE_THREAT_HEATMAP_SENSORS, True),
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="site_entity_settings",
            data_schema=data_schema,  # type: ignore[arg-type]
        )

    async def async_step_update_intervals(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle update interval configuration."""
        if user_input is not None:
            # Return merged options — HA sets entry.options from data param
            return self.async_create_entry(
                title="",
                data={
                    **self.config_entry.options,
                    CONF_DEVICE_SCAN_INTERVAL: user_input[CONF_DEVICE_SCAN_INTERVAL],
                    CONF_CLIENT_SCAN_INTERVAL: user_input[CONF_CLIENT_SCAN_INTERVAL],
                    CONF_APP_SCAN_INTERVAL: user_input[CONF_APP_SCAN_INTERVAL],
                },
            )

        # Get current values from options
        current_device = self.config_entry.options.get(
            CONF_DEVICE_SCAN_INTERVAL, DEFAULT_DEVICE_SCAN_INTERVAL
        )
        current_client = self.config_entry.options.get(
            CONF_CLIENT_SCAN_INTERVAL, DEFAULT_CLIENT_SCAN_INTERVAL
        )
        current_app = self.config_entry.options.get(
            CONF_APP_SCAN_INTERVAL, DEFAULT_APP_SCAN_INTERVAL
        )

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_DEVICE_SCAN_INTERVAL, default=current_device
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                ),
                vol.Required(
                    CONF_CLIENT_SCAN_INTERVAL, default=current_client
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                ),
                vol.Required(CONF_APP_SCAN_INTERVAL, default=current_app): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                ),
            }
        )

        return self.async_show_form(
            step_id="update_intervals",
            data_schema=data_schema,  # type: ignore[arg-type]
        )

    def _adopt_client_mac_spelling(self) -> None:
        """Respell selected MACs the way the client list spells them.

        Stored MACs may use another separator style than the client list, which
        would hide them from the form's selection.
        """
        by_canonical = {
            normalize_client_mac(c.get("mac", "")): c.get("mac", "")
            for c in self._available_clients
        }
        self._working_client_macs = [
            by_canonical.get(normalize_client_mac(mac), mac)
            for mac in self._working_client_macs or []
        ]

    def _unknown_selected_macs(self) -> set[str]:
        """Return selected client MACs that the controller does not list."""
        known = {c.get("mac", "") for c in self._available_clients}
        return set(self._working_client_macs or []) - known

    async def async_step_client_selection(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle client selection in options flow."""
        errors: dict[str, str] = {}

        if self._working_client_macs is None:
            self._working_client_macs = list(
                self.config_entry.options.get(CONF_SELECTED_CLIENTS, [])
            )

        if user_input is not None:
            # Merge the just-submitted (currently visible) selection into the
            # working set. Only overwrite the MACs that were actually shown
            # as options on the previous render — anything hidden behind the
            # SSID filter at that time is left untouched, so narrowing the
            # view doesn't silently drop selections on other SSIDs.
            previously_visible_macs = {
                c.get("mac", "")
                for c in filter_clients_by_ssids(
                    self._available_clients, self._ssid_filter
                )
            } | self._unknown_selected_macs()
            submitted_macs = user_input.get(CONF_SELECTED_CLIENTS, [])
            self._working_client_macs = [
                mac
                for mac in self._working_client_macs
                if mac not in previously_visible_macs
            ] + submitted_macs

            # If SSID filter was submitted, re-show with filtered list
            new_ssid_filter = user_input.get(CONF_SSID_FILTER, [])
            if new_ssid_filter != self._ssid_filter and self._available_clients:
                self._ssid_filter = new_ssid_filter
                # Fall through to re-show the form with filtered clients
            else:
                # Return merged options — HA sets entry.options from data param
                return self.async_create_entry(
                    title="",
                    data={
                        **self.config_entry.options,
                        CONF_SELECTED_CLIENTS: self._working_client_macs,
                    },
                )

        self._selected_site_ids = self.config_entry.data.get(CONF_SELECTED_SITES, [])

        # Fetch all clients only if not already loaded
        if not self._available_clients:
            try:
                self._ensure_api_client()
                all_clients = []
                for site_id in self._selected_site_ids:
                    clients_data = await self._get_clients(site_id)
                    all_clients.extend(clients_data)

                self._available_clients = all_clients
                self._adopt_client_mac_spelling()
            except Exception:
                _LOGGER.exception("Failed to fetch clients")
                errors["base"] = "cannot_connect"

        if not self._available_clients and not errors:
            # No clients available, return with empty selection
            return self.async_create_entry(title="", data=self.config_entry.options)

        # Extract available SSIDs for the filter
        available_ssids = extract_ssids_from_clients(self._available_clients)
        ssid_options = [
            SelectOptionDict(value=ssid, label=ssid) for ssid in available_ssids
        ]

        # Apply SSID filter to the displayed client list
        display_clients = filter_clients_by_ssids(
            self._available_clients, self._ssid_filter
        )

        # Create client selection options
        client_options = []
        visible_macs: set[str] = set()
        for client in display_clients:
            name = client.get("name") or client.get("hostName") or "Unknown"
            mac = client.get("mac", "")
            ip = client.get("ip", "N/A")
            online = "🟢" if client.get("active") else "🔴"

            visible_macs.add(mac)
            client_options.append(
                SelectOptionDict(
                    value=mac,
                    label=f"{online} {name} - {ip} ({mac})",
                )
            )
        # Keep offering selected clients the controller no longer lists, so a
        # save never drops them and the user can still deselect them (GH #96).
        for mac in sorted(self._unknown_selected_macs()):
            visible_macs.add(mac)
            client_options.append(SelectOptionDict(value=mac, label=f"⚪ {mac}"))

        # The field's default must only contain currently-valid options —
        # the full working selection (including SSIDs hidden by the current
        # filter) is preserved in self._working_client_macs regardless.
        field_default = [
            mac for mac in self._working_client_macs if mac in visible_macs
        ]

        schema_fields: dict[Any, Any] = {}
        if ssid_options:
            schema_fields[vol.Optional(CONF_SSID_FILTER, default=self._ssid_filter)] = (
                SelectSelector(
                    SelectSelectorConfig(
                        options=ssid_options,
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            )
        # A suggested value (not a default) lets the user clear the selection:
        # the frontend omits an emptied optional field, and a default would
        # silently restore the previous selection.
        schema_fields[
            vol.Optional(
                CONF_SELECTED_CLIENTS, description={"suggested_value": field_default}
            )
        ] = SelectSelector(
            SelectSelectorConfig(
                options=client_options,
                multiple=True,
                mode=SelectSelectorMode.DROPDOWN,
            )
        )

        data_schema = vol.Schema(schema_fields)

        return self.async_show_form(
            step_id="client_selection",
            data_schema=data_schema,  # type: ignore[arg-type]
            errors=errors,
            description_placeholders={
                "client_count": str(len(display_clients)),
                "selected_count": str(len(self._working_client_macs)),
            },
        )

    async def async_step_application_selection(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle application selection in options flow."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_app_ids = user_input.get(CONF_SELECTED_APPLICATIONS, [])

            # Return merged options — HA sets entry.options from data param
            return self.async_create_entry(
                title="",
                data={
                    **self.config_entry.options,
                    CONF_SELECTED_APPLICATIONS: selected_app_ids,
                },
            )

        self._selected_site_ids = self.config_entry.data.get(CONF_SELECTED_SITES, [])

        # Fetch applications from the first selected site
        try:
            self._ensure_api_client()
            if self._selected_site_ids:
                first_site_id = self._selected_site_ids[0]
                self._available_applications = await self._get_applications(
                    first_site_id
                )
        except Exception:
            _LOGGER.exception("Failed to fetch applications")
            errors["base"] = "cannot_connect"

        if not self._available_applications and not errors:
            # No applications available, return with empty selection
            return self.async_create_entry(title="", data=self.config_entry.options)

        # Get currently selected applications
        current_selection = self.config_entry.options.get(
            CONF_SELECTED_APPLICATIONS, []
        )

        # Create application selection options (sorted by family then name)
        app_options = []
        for app in sorted(
            self._available_applications,
            key=lambda x: (x.get("family", ""), x.get("application", "")),
        ):
            app_id = str(app.get("applicationId", ""))
            app_name = app.get("application", "Unknown")
            family = app.get("family", "Other")

            app_options.append(
                SelectOptionDict(
                    value=app_id,
                    label=f"{app_name} ({family})",
                )
            )

        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SELECTED_APPLICATIONS,
                    description={"suggested_value": current_selection},
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=app_options,
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="application_selection",
            data_schema=data_schema,  # type: ignore[arg-type]
            errors=errors,
            description_placeholders={
                "app_count": str(len(self._available_applications)),
                "selected_count": str(len(current_selection)),
            },
        )
