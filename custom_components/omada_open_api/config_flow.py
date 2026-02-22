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
    CONF_ACCESS_TOKEN,
    CONF_API_URL,
    CONF_APP_SCAN_INTERVAL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SCAN_INTERVAL,
    CONF_CLIENT_SECRET,
    CONF_CONTROLLER_TYPE,
    CONF_DEVICE_SCAN_INTERVAL,
    CONF_OMADA_ID,
    CONF_REFRESH_TOKEN,
    CONF_REGION,
    CONF_SELECTED_APPLICATIONS,
    CONF_SELECTED_CLIENTS,
    CONF_SELECTED_SITES,
    CONF_TOKEN_EXPIRES_AT,
    CONTROLLER_TYPE_CLOUD,
    CONTROLLER_TYPE_LOCAL,
    DEFAULT_APP_SCAN_INTERVAL,
    DEFAULT_CLIENT_SCAN_INTERVAL,
    DEFAULT_DEVICE_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    REGIONS,
)

_LOGGER = logging.getLogger(__name__)


class OmadaConfigFlow(ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg,misc]
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

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step where user selects controller type."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._controller_type = user_input[CONF_CONTROLLER_TYPE]

            if self._controller_type == CONTROLLER_TYPE_CLOUD:
                return await self.async_step_cloud()
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
            self._api_url = REGIONS[self._region]["api_url"]  # type: ignore[index]
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
            if not self._api_url.startswith(("http://", "https://")):  # type: ignore[union-attr]
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

            # Validate credentials by obtaining access token
            try:
                _LOGGER.debug("Attempting to get access token from %s", self._api_url)
                token_data = await self._get_access_token(
                    self._api_url,  # type: ignore[arg-type]
                    self._omada_id,  # type: ignore[arg-type]
                    self._client_id,  # type: ignore[arg-type]
                    self._client_secret,  # type: ignore[arg-type]
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

            except aiohttp.ClientError:
                _LOGGER.exception("Connection error during authentication")
                errors["base"] = "cannot_connect"
            except InvalidAuthError:
                _LOGGER.exception("Invalid authentication")
                errors["base"] = "invalid_auth"
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

            # Proceed to client selection
            return await self.async_step_clients()

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

    async def async_step_clients(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle client selection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._selected_client_macs = user_input.get(CONF_SELECTED_CLIENTS, [])

            # Proceed to application selection
            return await self.async_step_applications()

        # Fetch all clients from all selected sites
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
                data={
                    CONF_CONTROLLER_TYPE: self._controller_type,
                    CONF_API_URL: self._api_url,
                    CONF_OMADA_ID: self._omada_id,
                    CONF_CLIENT_ID: self._client_id,
                    CONF_CLIENT_SECRET: self._client_secret,
                    CONF_ACCESS_TOKEN: self._access_token,
                    CONF_REFRESH_TOKEN: self._refresh_token,
                    CONF_TOKEN_EXPIRES_AT: self._token_expires_at.isoformat(),  # type: ignore[union-attr]
                    CONF_SELECTED_SITES: self._selected_site_ids,
                },
                options={
                    CONF_SELECTED_CLIENTS: [],
                    CONF_SELECTED_APPLICATIONS: [],
                },
            )

        # Create client selection options
        client_options = []
        for client in self._available_clients[:200]:  # Limit to 200 to avoid UI issues
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
                "client_count": str(len(self._available_clients)),
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
                raise InvalidAuthError(f"API error: {error_msg}")

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

        # Request body for client query
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
                data={
                    CONF_CONTROLLER_TYPE: self._controller_type,
                    CONF_API_URL: self._api_url,
                    CONF_OMADA_ID: self._omada_id,
                    CONF_CLIENT_ID: self._client_id,
                    CONF_CLIENT_SECRET: self._client_secret,
                    CONF_ACCESS_TOKEN: self._access_token,
                    CONF_REFRESH_TOKEN: self._refresh_token,
                    CONF_TOKEN_EXPIRES_AT: self._token_expires_at.isoformat(),  # type: ignore[union-attr]
                    CONF_SELECTED_SITES: self._selected_site_ids,
                },
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
                data={
                    CONF_CONTROLLER_TYPE: self._controller_type,
                    CONF_API_URL: self._api_url,
                    CONF_OMADA_ID: self._omada_id,
                    CONF_CLIENT_ID: self._client_id,
                    CONF_CLIENT_SECRET: self._client_secret,
                    CONF_ACCESS_TOKEN: self._access_token,
                    CONF_REFRESH_TOKEN: self._refresh_token,
                    CONF_TOKEN_EXPIRES_AT: self._token_expires_at.isoformat(),  # type: ignore[union-attr]
                    CONF_SELECTED_SITES: self._selected_site_ids,
                },
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
                    self._api_url,  # type: ignore[arg-type]
                    omada_id,
                    client_id,
                    client_secret,
                )
                self._access_token = token_data["accessToken"]
                self._refresh_token = token_data["refreshToken"]
                self._token_expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(
                    seconds=token_data["expiresIn"]
                )
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
                return self._show_reconfigure_form(reconfigure_entry, errors)
            except InvalidAuthError:
                errors["base"] = "invalid_auth"
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

            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except InvalidAuthError:
                errors["base"] = "invalid_auth"
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


class OmadaOptionsFlowHandler(OptionsFlow):  # type: ignore[misc]
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
            ],
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

        # Fetch all clients from all selected sites
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

        # Create client selection options
        client_options = []
        for client in self._available_clients[:200]:  # Limit to 200
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
                vol.Optional(
                    CONF_SELECTED_CLIENTS, default=current_selection
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=client_options,
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="client_selection",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "client_count": str(len(self._available_clients)),
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

        # Request body for client query
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
