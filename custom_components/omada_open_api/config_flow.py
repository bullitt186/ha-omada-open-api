"""Config flow for Omada Open API integration."""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

import aiohttp
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
import voluptuous as vol

from .const import (
    AUTH_MODE_OPENAPI,
    AUTH_MODE_WEB_SESSION,
    CONF_ACCESS_TOKEN,
    CONF_API_URL,
    CONF_APP_SCAN_INTERVAL,
    CONF_AUTH_MODE,
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
    DEFAULT_CLIENT_SCAN_INTERVAL,
    DEFAULT_DEVICE_SCAN_INTERVAL,
    DEFAULT_DISCONNECT_TIMEOUT,
    DEFAULT_TIMEOUT,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    REGIONS,
)

_LOGGER = logging.getLogger(__name__)


def _classify_connection_error(err: aiohttp.ClientError) -> str:
    """Classify an aiohttp connection error into a specific error key.

    Returns the most specific error key for the given exception.
    """
    try:
        error_message = str(err).lower()
    except Exception:  # noqa: BLE001
        error_message = repr(err).lower()

    os_error = err.__cause__ or err.__context__
    try:
        os_message = str(os_error).lower() if os_error else ""
    except Exception:  # noqa: BLE001
        os_message = repr(os_error).lower() if os_error else ""

    combined = f"{error_message} {os_message}"

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


def _invalid_auth_error_key(err: InvalidAuthError) -> str:
    """Map an InvalidAuthError to the most specific translation error key."""
    if err.error_code == _CONTROLLER_ID_NOT_FOUND_ERROR_CODE:
        return "controller_id_not_found_free_tier"
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
        Filtered list of clients.

    """
    if not ssid_filter:
        return clients
    filter_set = set(ssid_filter)
    return [c for c in clients if not c.get("wireless") or c.get("ssid") in filter_set]


class OmadaConfigFlow(ConfigFlow, domain=DOMAIN):
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
        # Fusion-specific
        self._fusion_username: str | None = None
        self._fusion_password: str | None = None
        self._fusion_csrf_token: str | None = None
        self._fusion_session: aiohttp.ClientSession | None = None

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
                ): vol.In(
                    {
                        CONTROLLER_TYPE_LOCAL: "Self-Hosted (Local Controller)",
                        CONTROLLER_TYPE_CLOUD: "Cloud-Hosted (TP-Link Cloud)",
                        CONTROLLER_TYPE_FUSION: "Fusion Gateway (Built-in Controller)",
                    }
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle cloud controller region selection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._region = user_input[CONF_REGION]
            self._api_url = REGIONS[self._region]["api_url"]
            return await self.async_step_credentials()

        # Create schema for region selection
        data_schema = vol.Schema(
            {
                vol.Required(CONF_REGION): vol.In(
                    {key: value["name"] for key, value in REGIONS.items()}
                ),
            }
        )

        return self.async_show_form(
            step_id="cloud",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_local(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle local controller URL input."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._api_url = user_input[CONF_API_URL].rstrip("/")
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
            }
        )

        return self.async_show_form(
            step_id="local",
            data_schema=data_schema,
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
                    # Auto-detect Omada CID
                    omada_id = await self._get_omada_cid(api_url)

                    # Validate credentials via web login
                    csrf_token = await self._fusion_login(
                        api_url, omada_id, username, password
                    )

                    # Store for later steps
                    self._api_url = api_url
                    self._omada_id = omada_id
                    self._controller_type = CONTROLLER_TYPE_FUSION
                    self._fusion_username = username
                    self._fusion_password = password
                    self._fusion_csrf_token = csrf_token
                    # Set access_token to the CSRF token so existing
                    # _get_clients/_get_applications can work via header override
                    self._access_token = csrf_token

                    # Prevent duplicate entries
                    await self.async_set_unique_id(f"fusion_{omada_id}")
                    self._abort_if_unique_id_configured()

                    # Fetch sites using existing session/csrf
                    sites = await self._get_sites_fusion(api_url, omada_id, csrf_token)
                    if not sites:
                        errors["base"] = "no_sites"
                    else:
                        self._available_sites = sites
                        # Auto-select if single site
                        if len(sites) == 1:
                            self._selected_site_ids = [sites[0]["siteId"]]
                            return await self.async_step_ssid_filter()
                        return await self.async_step_sites()

                except TimeoutError:
                    errors["base"] = "timeout"
                except aiohttp.ClientError as err:
                    _LOGGER.warning(
                        "Fusion connection error (%s): %s",
                        type(err).__name__,
                        err,
                    )
                    error_key = _classify_connection_error(err)
                    errors["base"] = error_key
                except InvalidAuthError:
                    errors["base"] = "invalid_auth"
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
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "example_url": "https://192.168.1.1",
            },
        )

    def _get_fusion_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session with unsafe cookie jar for Fusion.

        Fusion gateways are accessed by IP address, requiring unsafe=True
        on the cookie jar to persist session cookies.
        """
        if self._fusion_session is None:
            connector = aiohttp.TCPConnector(ssl=False)
            jar = aiohttp.CookieJar(unsafe=True)
            self._fusion_session = aiohttp.ClientSession(
                connector=connector, cookie_jar=jar
            )
        return self._fusion_session

    async def _get_omada_cid(self, api_url: str) -> str:
        """Auto-detect Omada controller ID from /api/info endpoint."""
        session = self._get_fusion_session()
        url = f"{api_url}/api/info"
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)
        ) as response:
            if response.status != 200:
                raise InvalidAuthError("Failed to reach controller info endpoint")
            result = await response.json(content_type=None)
            if result.get("errorCode") != 0:
                raise InvalidAuthError(
                    f"Controller info error: {result.get('msg', 'Unknown')}"
                )
            omada_cid = result.get("result", {}).get("omadacId")
            if not omada_cid:
                raise InvalidAuthError("Could not detect Omada Controller ID")
            return omada_cid  # type: ignore[no-any-return]

    async def _fusion_login(
        self, api_url: str, omada_id: str, username: str, password: str
    ) -> str:
        """Perform Fusion web login and return CSRF token."""
        session = self._get_fusion_session()
        url = f"{api_url}/{omada_id}/api/v2/login"
        data = {"username": username, "password": password}
        async with session.post(
            url, json=data, timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)
        ) as response:
            result = await response.json(content_type=None)
            if result.get("errorCode") != 0:
                raise InvalidAuthError(
                    f"Login failed: {result.get('msg', 'Unknown error')}",
                    error_code=result.get("errorCode"),
                )
            return result["result"]["token"]  # type: ignore[no-any-return]

    async def _get_sites_fusion(
        self, api_url: str, omada_id: str, csrf_token: str
    ) -> list[dict[str, Any]]:
        """Fetch sites using Fusion web-session auth."""
        session = self._get_fusion_session()
        url = f"{api_url}/openapi/v1/{omada_id}/sites"
        headers = {
            "Csrf-Token": csrf_token,
            "Omada-Request-Source": "web-local",
            "Content-Type": "application/json",
        }
        params = {"pageSize": 100, "page": 1}
        async with session.get(
            url,
            headers=headers,
            params=params,
            timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
        ) as response:
            if response.status != 200:
                _LOGGER.warning("Fusion sites: HTTP %s", response.status)
                return []
            result = await response.json(content_type=None)
            if result.get("errorCode") != 0:
                _LOGGER.warning(
                    "Fusion sites: errorCode %s: %s",
                    result.get("errorCode"),
                    result.get("msg"),
                )
                return []
            return result.get("result", {}).get("data", [])  # type: ignore[no-any-return]

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

            # Validate credentials by obtaining access token
            try:
                _LOGGER.debug("Attempting to get access token from %s", self._api_url)
                token_data = await self._get_access_token(
                    self._api_url,  # type: ignore[arg-type]
                    self._omada_id,
                    self._client_id,
                    self._client_secret,
                )
                _LOGGER.debug("Successfully obtained access token")

                # Store token data
                self._access_token = token_data["accessToken"]
                self._refresh_token = token_data["refreshToken"]
                self._token_expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(
                    seconds=token_data["expiresIn"]
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
            except aiohttp.ClientError as err:
                error_key = _classify_connection_error(err)
                _LOGGER.warning(
                    "Connection error during authentication (%s): %s",
                    error_key,
                    err,
                )
                errors["base"] = error_key
            except InvalidAuthError as err:
                _LOGGER.warning("Invalid authentication for %s", self._api_url)
                errors["base"] = _invalid_auth_error_key(err)
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
        if self._controller_type == CONTROLLER_TYPE_CLOUD:
            description_placeholders["controller_info"] = (
                f"Region: {REGIONS[self._region]['name']}"  # type: ignore[index]
            )
        else:
            description_placeholders["controller_info"] = f"URL: {self._api_url}"

        return self.async_show_form(
            step_id="credentials",
            data_schema=data_schema,
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
            data_schema=data_schema,
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
            CONF_TOKEN_EXPIRES_AT: self._token_expires_at.isoformat()
            if self._token_expires_at
            else "",
            CONF_SELECTED_SITES: self._selected_site_ids,
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
            data_schema=data_schema,
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
        for client in display_clients[:200]:  # Limit to 200 to avoid UI issues
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
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "client_count": str(len(display_clients)),
            },
        )

    async def _get_access_token(
        self,
        api_url: str,
        omada_id: str,
        client_id: str,
        client_secret: str,
    ) -> dict[str, Any]:
        """Obtain access token using client credentials flow.

        Args:
            api_url: Base API URL (cloud or local controller)
            omada_id: The Omada controller ID (MSP ID or Customer ID)
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret

        Returns:
            Dictionary containing access token data

        Raises:
            InvalidAuth: If authentication fails
            aiohttp.ClientError: If connection fails

        """
        _LOGGER.debug("Getting access token from %s", api_url)
        session = async_get_clientsession(self.hass, verify_ssl=False)

        # Use client credentials grant type as specified in Omada API docs
        url = f"{api_url}/openapi/authorize/token"
        params = {"grant_type": "client_credentials"}
        data = {
            "omadacId": omada_id,
            "client_id": client_id,
            "client_secret": "***",  # Don't log secret
        }
        _LOGGER.debug("POST %s with params %s and data %s", url, params, data)

        # Use actual client_secret for the request
        data["client_secret"] = client_secret

        async with session.post(
            url,
            params=params,
            json=data,
            timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
        ) as response:
            _LOGGER.debug("Response status: %s", response.status)
            if response.status == 401:
                raise InvalidAuthError("Invalid client credentials")
            if response.status != 200:
                response_text = await response.text()
                _LOGGER.error("HTTP error %s: %s", response.status, response_text)
                response.raise_for_status()

            result = await response.json()

            # Check for API error codes
            if result.get("errorCode") != 0:
                error_code = result.get("errorCode")
                error_msg = result.get("msg", "Unknown error")
                _LOGGER.error(
                    "API error during authentication: %s - %s", error_code, error_msg
                )
                raise InvalidAuthError(f"API error: {error_msg}", error_code=error_code)

            return result["result"]  # type: ignore[no-any-return]

    async def _get_sites(self) -> list[dict[str, Any]]:
        """Fetch available sites from the controller.

        Returns:
            List of site dictionaries

        Raises:
            aiohttp.ClientError: If connection fails

        """
        session = async_get_clientsession(self.hass, verify_ssl=False)
        url = f"{self._api_url}/openapi/v1/{self._omada_id}/sites"
        headers = {"Authorization": f"AccessToken={self._access_token}"}
        # Add pagination parameters as shown in the Omada API documentation
        params = {"pageSize": 100, "page": 1}

        _LOGGER.debug("Fetching sites from %s with params %s", url, params)

        async with session.get(
            url,
            headers=headers,
            params=params,
            timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
        ) as response:
            _LOGGER.debug("Sites endpoint response status: %s", response.status)
            if response.status != 200:
                response_text = await response.text()
                _LOGGER.error("Sites API error %s: %s", response.status, response_text)
                response.raise_for_status()

            result = await response.json()

            if result.get("errorCode") != 0:
                error_msg = result.get("msg", "Unknown error")
                raise InvalidAuthError(f"API error: {error_msg}")

            return result["result"]["data"]  # type: ignore[no-any-return]

    def _build_api_headers(self) -> dict[str, str]:
        """Build API headers based on current auth mode."""
        if self._controller_type == CONTROLLER_TYPE_FUSION and self._fusion_csrf_token:
            return {
                "Csrf-Token": self._fusion_csrf_token,
                "Omada-Request-Source": "web-local",
                "Content-Type": "application/json",
            }
        return {
            "Authorization": f"AccessToken={self._access_token}",
            "Content-Type": "application/json",
        }

    async def _get_clients(self, site_id: str) -> list[dict[str, Any]]:
        """Fetch all clients for a site.

        Args:
            site_id: Site ID to get clients for

        Returns:
            List of client dictionaries

        Raises:
            aiohttp.ClientError: If connection fails

        """
        session = async_get_clientsession(self.hass, verify_ssl=False)
        url = f"{self._api_url}/openapi/v2/{self._omada_id}/sites/{site_id}/clients"
        headers = self._build_api_headers()

        # scope=0 is intentional here: the config / options flow must
        # show all known clients (including offline) so the user can
        # choose which ones to track.  Polling coordinators use scope=1
        # (online only) to avoid controller-side wifiMode warnings.
        body = {
            "page": 1,
            "pageSize": 200,  # Get first 200 clients
            "scope": 0,  # 0: all clients (online + offline)
            "filters": {},
        }

        _LOGGER.debug("Fetching clients from site %s", site_id)

        async with session.post(
            url,
            headers=headers,
            json=body,
            timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
        ) as response:
            _LOGGER.debug("Clients endpoint response status: %s", response.status)
            if response.status != 200:
                response_text = await response.text()
                _LOGGER.error(
                    "Clients API error %s: %s", response.status, response_text
                )
                response.raise_for_status()

            result = await response.json()

            if result.get("errorCode") != 0:
                error_msg = result.get("msg", "Unknown error")
                raise InvalidAuthError(f"API error: {error_msg}")

            return result["result"]["data"]  # type: ignore[no-any-return]

    async def _get_applications(self, site_id: str) -> list[dict[str, Any]]:
        """Fetch all available applications for DPI tracking.

        Args:
            site_id: Site ID to get applications for

        Returns:
            List of application dictionaries with applicationId, applicationName, etc.

        Raises:
            aiohttp.ClientError: If connection fails

        """
        session = async_get_clientsession(self.hass, verify_ssl=False)
        url = f"{self._api_url}/openapi/v1/{self._omada_id}/sites/{site_id}/applicationControl/applications"
        headers = self._build_api_headers()

        _LOGGER.debug("Fetching applications from site %s", site_id)

        all_apps: list[dict[str, Any]] = []
        page = 1
        page_size = 1000
        total_rows = 0

        while True:
            params = {
                "page": page,
                "pageSize": page_size,
            }

            async with session.get(
                url,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
            ) as response:
                _LOGGER.debug(
                    "Applications endpoint response status: %s (page %d)",
                    response.status,
                    page,
                )
                if response.status != 200:
                    response_text = await response.text()
                    _LOGGER.error(
                        "Applications API error %s: %s", response.status, response_text
                    )
                    response.raise_for_status()

                result = await response.json()

                if result.get("errorCode") != 0:
                    error_msg = result.get("msg", "Unknown error")
                    # Applications might not be supported, return empty list
                    _LOGGER.warning("Applications API error: %s", error_msg)
                    return []

                page_data = result["result"]["data"]
                total_rows = result["result"].get("totalRows", 0)
                all_apps.extend(page_data)

                # Check if we've fetched all applications
                if len(all_apps) >= total_rows or len(page_data) < page_size:
                    break

                page += 1

        _LOGGER.info(
            "Fetched %d applications (total: %d) from site %s across %d pages",
            len(all_apps),
            total_rows,
            site_id,
            page,
        )
        return all_apps

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
            data_schema=data_schema,
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

            try:
                token_data = await self._get_access_token(
                    self._api_url,
                    omada_id,
                    client_id,
                    client_secret,
                )
                self._access_token = token_data["accessToken"]
                self._refresh_token = token_data["refreshToken"]
                self._token_expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(
                    seconds=token_data["expiresIn"]
                )
            except TimeoutError:
                _LOGGER.warning("Connection timed out to %s", self._api_url)
                errors["base"] = "timeout"
                return self._show_reconfigure_form(reconfigure_entry, errors)
            except aiohttp.ClientError as err:
                error_key = _classify_connection_error(err)
                _LOGGER.warning(
                    "Connection error during reconfigure (%s): %s",
                    error_key,
                    err,
                )
                errors["base"] = error_key
                return self._show_reconfigure_form(reconfigure_entry, errors)
            except InvalidAuthError as err:
                errors["base"] = _invalid_auth_error_key(err)
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
                ): vol.In(
                    {
                        CONTROLLER_TYPE_CLOUD: "Cloud",
                        CONTROLLER_TYPE_LOCAL: "Local",
                    }
                ),
                vol.Optional(
                    CONF_REGION,
                    default=entry.data.get(CONF_REGION, "us"),
                ): vol.In({key: info["name"] for key, info in REGIONS.items()}),
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

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=data_schema,
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
                        CONF_TOKEN_EXPIRES_AT: (
                            self._token_expires_at.isoformat()
                            if self._token_expires_at
                            else ""
                        ),
                        CONF_SELECTED_SITES: selected,
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
            data_schema=data_schema,
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
        _LOGGER.debug("Reauth flow started with entry_data: %s", entry_data)
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
        _LOGGER.debug("Reauth confirm step called with user_input: %s", user_input)
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        _LOGGER.debug("Reauth entry retrieved: %s", reauth_entry.title)

        if user_input is not None:
            # Use existing config entry data for non-credential fields
            api_url = reauth_entry.data[CONF_API_URL]
            omada_id = user_input.get(CONF_OMADA_ID, reauth_entry.data[CONF_OMADA_ID])
            client_id = user_input[CONF_CLIENT_ID]
            client_secret = user_input[CONF_CLIENT_SECRET]

            try:
                # Get new tokens
                token_data = await self._get_access_token(
                    api_url,
                    omada_id,
                    client_id,
                    client_secret,
                )

                # Update config entry with new credentials
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={
                        CONF_CLIENT_ID: client_id,
                        CONF_CLIENT_SECRET: client_secret,
                        CONF_OMADA_ID: omada_id,
                        CONF_ACCESS_TOKEN: token_data["accessToken"],
                        CONF_REFRESH_TOKEN: token_data["refreshToken"],
                        CONF_TOKEN_EXPIRES_AT: (
                            dt.datetime.now(dt.UTC)
                            + dt.timedelta(seconds=token_data["expiresIn"])
                        ).isoformat(),
                    },
                )

            except TimeoutError:
                _LOGGER.warning("Connection timed out during reauth")
                errors["base"] = "timeout"
            except aiohttp.ClientError as err:
                error_key = _classify_connection_error(err)
                _LOGGER.warning(
                    "Connection error during reauth (%s): %s", error_key, err
                )
                errors["base"] = error_key
            except InvalidAuthError as err:
                errors["base"] = _invalid_auth_error_key(err)
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
            data_schema=data_schema,
            errors=errors,
        )


class OmadaOptionsFlowHandler(OptionsFlow):
    """Handle options flow for Omada Open API."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__()
        self._api_url: str | None = None
        self._omada_id: str | None = None
        self._access_token: str | None = None
        self._selected_site_ids: list[str] = []
        self._available_clients: list[dict[str, Any]] = []
        self._available_applications: list[dict[str, Any]] = []
        self._ssid_filter: list[str] = []

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
            ],
        )

    async def async_step_tracker_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle device tracker settings (disconnect timeout)."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    **self.config_entry.options,
                    CONF_DISCONNECT_TIMEOUT: user_input[CONF_DISCONNECT_TIMEOUT],
                },
            )

        current_timeout = self.config_entry.options.get(
            CONF_DISCONNECT_TIMEOUT, DEFAULT_DISCONNECT_TIMEOUT
        )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_DISCONNECT_TIMEOUT, default=current_timeout): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=60)
                ),
            }
        )

        return self.async_show_form(
            step_id="tracker_settings",
            data_schema=data_schema,
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
            data_schema=data_schema,
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
            data_schema=data_schema,
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
            data_schema=data_schema,
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
            data_schema=data_schema,
        )

    async def async_step_client_selection(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle client selection in options flow."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # If SSID filter was submitted, re-show with filtered list
            new_ssid_filter = user_input.get(CONF_SSID_FILTER, [])
            if new_ssid_filter != self._ssid_filter and self._available_clients:
                self._ssid_filter = new_ssid_filter
                # Fall through to re-show the form with filtered clients
            else:
                selected_client_macs = user_input.get(CONF_SELECTED_CLIENTS, [])
                # Return merged options — HA sets entry.options from data param
                return self.async_create_entry(
                    title="",
                    data={
                        **self.config_entry.options,
                        CONF_SELECTED_CLIENTS: selected_client_macs,
                    },
                )

        # Get credentials from config entry
        self._api_url = self.config_entry.data[CONF_API_URL]
        self._omada_id = self.config_entry.data[CONF_OMADA_ID]
        self._access_token = self.config_entry.data[CONF_ACCESS_TOKEN]
        self._selected_site_ids = self.config_entry.data.get(CONF_SELECTED_SITES, [])

        # Fetch all clients only if not already loaded
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

        if not self._available_clients and not errors:
            # No clients available, return with empty selection
            return self.async_create_entry(title="", data=self.config_entry.options)

        # Get currently selected clients
        current_selection = self.config_entry.options.get(CONF_SELECTED_CLIENTS, [])

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
        for client in display_clients[:200]:  # Limit to 200
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
        schema_fields[
            vol.Optional(CONF_SELECTED_CLIENTS, default=current_selection)
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
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "client_count": str(len(display_clients)),
                "selected_count": str(len(current_selection)),
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

        # Get credentials from config entry
        self._api_url = self.config_entry.data[CONF_API_URL]
        self._omada_id = self.config_entry.data[CONF_OMADA_ID]
        self._access_token = self.config_entry.data[CONF_ACCESS_TOKEN]
        self._selected_site_ids = self.config_entry.data.get(CONF_SELECTED_SITES, [])

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
                    CONF_SELECTED_APPLICATIONS, default=current_selection
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
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "app_count": str(len(self._available_applications)),
                "selected_count": str(len(current_selection)),
            },
        )

    async def _get_clients(self, site_id: str) -> list[dict[str, Any]]:
        """Fetch all clients for a site.

        Args:
            site_id: Site ID to get clients for

        Returns:
            List of client dictionaries

        Raises:
            aiohttp.ClientError: If connection fails

        """
        session = async_get_clientsession(self.hass, verify_ssl=False)
        url = f"{self._api_url}/openapi/v2/{self._omada_id}/sites/{site_id}/clients"
        headers = {
            "Authorization": f"AccessToken={self._access_token}",
            "Content-Type": "application/json",
        }

        # scope=0 is intentional here: the config / options flow must
        # show all known clients (including offline) so the user can
        # choose which ones to track.  Polling coordinators use scope=1
        # (online only) to avoid controller-side wifiMode warnings.
        body = {
            "page": 1,
            "pageSize": 200,  # Get first 200 clients
            "scope": 0,  # 0: all clients (online + offline)
            "filters": {},
        }

        _LOGGER.debug("Fetching clients from site %s", site_id)

        async with session.post(
            url,
            headers=headers,
            json=body,
            timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
        ) as response:
            _LOGGER.debug("Clients endpoint response status: %s", response.status)
            if response.status != 200:
                response_text = await response.text()
                _LOGGER.error(
                    "Clients API error %s: %s", response.status, response_text
                )
                response.raise_for_status()

            result = await response.json()

            if result.get("errorCode") != 0:
                error_msg = result.get("msg", "Unknown error")
                raise InvalidAuthError(f"API error: {error_msg}")

            return result["result"]["data"]  # type: ignore[no-any-return]

    async def _get_applications(self, site_id: str) -> list[dict[str, Any]]:
        """Fetch all available applications for DPI tracking.

        Args:
            site_id: Site ID to get applications for

        Returns:
            List of application dictionaries

        Raises:
            aiohttp.ClientError: If connection fails

        """
        session = async_get_clientsession(self.hass, verify_ssl=False)
        url = f"{self._api_url}/openapi/v1/{self._omada_id}/sites/{site_id}/applicationControl/applications"
        headers = {
            "Authorization": f"AccessToken={self._access_token}",
            "Content-Type": "application/json",
        }

        _LOGGER.debug("Fetching applications from site %s", site_id)

        all_apps: list[dict[str, Any]] = []
        page = 1
        page_size = 1000
        total_rows = 0

        while True:
            params = {
                "page": page,
                "pageSize": page_size,
            }

            async with session.get(
                url,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
            ) as response:
                _LOGGER.debug(
                    "Applications endpoint response status: %s (page %d)",
                    response.status,
                    page,
                )
                if response.status != 200:
                    response_text = await response.text()
                    _LOGGER.error(
                        "Applications API error %s: %s", response.status, response_text
                    )
                    response.raise_for_status()

                result = await response.json()

                if result.get("errorCode") != 0:
                    error_msg = result.get("msg", "Unknown error")
                    _LOGGER.warning("Applications API error: %s", error_msg)
                    return []

                page_data = result["result"]["data"]
                total_rows = result["result"].get("totalRows", 0)
                all_apps.extend(page_data)

                # Check if we've fetched all applications
                if len(all_apps) >= total_rows or len(page_data) < page_size:
                    break

                page += 1

        _LOGGER.info(
            "Fetched %d applications (total: %d) from site %s across %d pages",
            len(all_apps),
            total_rows,
            site_id,
            page,
        )
        return all_apps


class InvalidAuthError(Exception):
    """Error to indicate authentication failure."""

    def __init__(self, message: str, error_code: int | None = None) -> None:
        """Initialize with the message and optional Omada API error code."""
        super().__init__(message)
        self.error_code = error_code
