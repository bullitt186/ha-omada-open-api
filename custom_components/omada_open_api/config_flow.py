"""Config flow for Omada Open API integration."""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
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
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_CONTROLLER_TYPE,
    CONF_OMADA_ID,
    CONF_REFRESH_TOKEN,
    CONF_REGION,
    CONF_SELECTED_SITES,
    CONF_TOKEN_EXPIRES_AT,
    CONTROLLER_TYPE_CLOUD,
    CONTROLLER_TYPE_LOCAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
    REGIONS,
)

_LOGGER = logging.getLogger(__name__)


class OmadaConfigFlow(ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg,misc]
    """Handle a config flow for Omada Open API."""

    VERSION = 1
    MINOR_VERSION = 1

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
            selected_site_ids = user_input[CONF_SELECTED_SITES]

            # Get title from first selected site or use controller type
            if selected_site_ids:
                first_site = next(
                    site
                    for site in self._available_sites
                    if site["siteId"] in selected_site_ids
                )
                title = f"Omada - {first_site['name']}"
                if len(selected_site_ids) > 1:
                    title += f" (+{len(selected_site_ids) - 1})"
            else:
                title = "Omada Controller"

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
                    CONF_SELECTED_SITES: selected_site_ids,
                },
            )

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


class InvalidAuthError(Exception):
    """Error to indicate authentication failure."""
