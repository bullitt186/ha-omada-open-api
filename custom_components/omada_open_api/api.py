"""API client for Omada Open API."""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from typing import TYPE_CHECKING, Any

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN_EXPIRES_AT,
    DEFAULT_TIMEOUT,
    TOKEN_EXPIRY_BUFFER,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class OmadaApiClient:
    """Omada Open API client."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api_url: str,
        omada_id: str,
        client_id: str,
        client_secret: str,
        access_token: str,
        refresh_token: str,
        token_expires_at: dt.datetime,
    ) -> None:
        """Initialize the API client.

        Args:
            hass: Home Assistant instance
            config_entry: Config entry for storing updated tokens
            api_url: Base API URL (cloud or local controller)
            omada_id: Omada controller ID
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
            access_token: Current access token
            refresh_token: Current refresh token
            token_expires_at: When the access token expires

        """
        self._hass = hass
        self._config_entry = config_entry
        self._api_url = api_url.rstrip("/")
        self._omada_id = omada_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._token_expires_at = token_expires_at
        self._session = async_get_clientsession(hass, verify_ssl=False)
        self._token_refresh_lock = asyncio.Lock()

    @property
    def api_url(self) -> str:
        """Return the API URL."""
        return self._api_url

    async def _ensure_valid_token(self) -> None:
        """Ensure we have a valid access token, refresh if needed.

        Raises:
            OmadaApiException: If token refresh fails

        """
        async with self._token_refresh_lock:
            # Check if token needs refresh (5 minutes before expiry)
            now = dt.datetime.now(dt.UTC)
            buffer = dt.timedelta(seconds=TOKEN_EXPIRY_BUFFER)
            if now >= self._token_expires_at - buffer:
                _LOGGER.debug("Access token expired or expiring soon, refreshing")
                await self._refresh_access_token()

    async def _update_config_entry(self) -> None:
        """Update config entry with new token data."""
        self._hass.config_entries.async_update_entry(
            self._config_entry,
            data={
                **self._config_entry.data,
                CONF_ACCESS_TOKEN: self._access_token,
                CONF_REFRESH_TOKEN: self._refresh_token,
                CONF_TOKEN_EXPIRES_AT: self._token_expires_at.isoformat(),
            },
        )
        _LOGGER.debug("Config entry updated with new tokens")

    async def _get_fresh_tokens(self) -> None:
        """Get fresh tokens using client credentials (for expired refresh tokens).

        Raises:
            OmadaApiException: If getting fresh tokens fails

        """
        _LOGGER.info(
            "Refresh token expired, requesting fresh tokens using client credentials"
        )
        url = f"{self._api_url}/openapi/authorize/token"
        params = {
            "grant_type": "client_credentials",
            "omadacId": self._omada_id,
        }
        data = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }

        try:
            async with self._session.post(
                url,
                params=params,
                json=data,
                timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
            ) as response:
                if response.status != 200:
                    raise OmadaApiAuthError(
                        f"Failed to get fresh tokens with status {response.status}"
                    )

                result = await response.json()

                if result.get("errorCode") != 0:
                    error_msg = result.get("msg", "Unknown error")
                    error_code = result.get("errorCode")
                    _LOGGER.error(
                        "API error getting fresh tokens: %s - %s",
                        error_code,
                        error_msg,
                    )
                    raise OmadaApiAuthError(f"API error: {error_msg}")

                token_data = result["result"]
                self._access_token = token_data["accessToken"]
                self._refresh_token = token_data["refreshToken"]
                self._token_expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(
                    seconds=token_data["expiresIn"]
                )

                _LOGGER.info("Fresh tokens obtained successfully")

                # Persist to config entry
                await self._update_config_entry()

        except aiohttp.ClientError as err:
            raise OmadaApiError(
                f"Connection error getting fresh tokens: {err}"
            ) from err

    async def _refresh_access_token(self) -> None:
        """Refresh the access token using refresh token.

        If refresh token is expired, automatically gets fresh tokens using client credentials.

        Raises:
            OmadaApiException: If refresh fails

        """
        url = f"{self._api_url}/openapi/authorize/token"
        params = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
        }
        data = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }

        try:
            async with self._session.post(
                url,
                params=params,
                json=data,
                timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
            ) as response:
                if response.status == 401:
                    # Refresh token expired, get fresh tokens automatically
                    _LOGGER.debug(
                        "Refresh token expired, getting fresh tokens automatically"
                    )
                    await self._get_fresh_tokens()
                    return

                if response.status != 200:
                    raise OmadaApiError(
                        f"Token refresh failed with status {response.status}"
                    )

                result = await response.json()

                if result.get("errorCode") != 0:
                    error_msg = result.get("msg", "Unknown error")
                    error_code = result.get("errorCode")

                    # Error code -44114: Refresh token expired
                    if error_code == -44114:
                        _LOGGER.info(
                            "Refresh token expired (error %s), getting fresh tokens automatically",
                            error_code,
                        )
                        await self._get_fresh_tokens()
                        return

                    _LOGGER.error(
                        "API error during token refresh: %s - %s",
                        error_code,
                        error_msg,
                    )
                    raise OmadaApiAuthError(f"API error: {error_msg}")

                token_data = result["result"]
                self._access_token = token_data["accessToken"]
                self._refresh_token = token_data["refreshToken"]
                self._token_expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(
                    seconds=token_data["expiresIn"]
                )

                _LOGGER.debug("Access token refreshed successfully")

                # Persist to config entry
                await self._update_config_entry()

        except aiohttp.ClientError as err:
            raise OmadaApiError(
                f"Connection error during token refresh: {err}"
            ) from err

    async def get_sites(self) -> list[dict[str, Any]]:
        """Get list of sites from Omada controller.

        Returns:
            List of site dictionaries

        Raises:
            OmadaApiException: If API request fails

        """
        await self._ensure_valid_token()

        url = f"{self._api_url}/openapi/v1/{self._omada_id}/sites"
        headers = {"Authorization": f"AccessToken={self._access_token}"}
        # Add pagination parameters as required by Omada API
        params = {"pageSize": 100, "page": 1}

        try:
            async with self._session.get(
                url,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
            ) as response:
                if response.status == 401:
                    # Token might have expired between check and request, try once more
                    await self._refresh_access_token()
                    headers["Authorization"] = f"AccessToken={self._access_token}"
                    async with self._session.get(
                        url,
                        headers=headers,
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
                    ) as retry_response:
                        if retry_response.status != 200:
                            raise OmadaApiError(
                                f"Failed to get sites: {retry_response.status}"
                            )
                        result = await retry_response.json()
                elif response.status != 200:
                    raise OmadaApiError(f"Failed to get sites: {response.status}")
                else:
                    result = await response.json()

                if result.get("errorCode") != 0:
                    error_msg = result.get("msg", "Unknown error")
                    raise OmadaApiError(f"API error: {error_msg}")

                return result["result"]["data"]  # type: ignore[no-any-return]

        except aiohttp.ClientError as err:
            raise OmadaApiError(f"Connection error: {err}") from err

    async def get_devices(self, site_id: str) -> list[dict[str, Any]]:
        """Fetch devices for a specific site.

        Args:
            site_id: The site ID to fetch devices for

        Returns:
            List of device dictionaries

        Raises:
            OmadaApiError: If fetching devices fails

        """
        await self._ensure_valid_token()

        session = async_get_clientsession(self._hass, verify_ssl=False)
        url = f"{self._api_url}/openapi/v1/{self._omada_id}/sites/{site_id}/devices"
        headers = {"Authorization": f"AccessToken={self._access_token}"}
        # Add pagination parameters
        params = {"pageSize": 100, "page": 1}

        _LOGGER.debug("Fetching devices from %s with params %s", url, params)

        try:
            async with session.get(
                url,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
            ) as response:
                if response.status != 200:
                    response_text = await response.text()
                    _LOGGER.error("HTTP error %s: %s", response.status, response_text)
                    response.raise_for_status()

                result = await response.json()

                # Check for API error codes
                if result.get("errorCode") != 0:
                    error_msg = result.get("msg", "Unknown error")
                    raise OmadaApiError(f"API error: {error_msg}")

                return result["result"]["data"]  # type: ignore[no-any-return]

        except aiohttp.ClientError as err:
            raise OmadaApiError(f"Connection error: {err}") from err

    async def get_device_uplink_info(
        self, site_id: str, device_macs: list[str]
    ) -> list[dict[str, Any]]:
        """Get uplink information for specified devices.

        Args:
            site_id: Site ID
            device_macs: List of device MAC addresses to query

        Returns:
            List of uplink info dictionaries containing uplinkDeviceMac,
            uplinkDeviceName, uplinkDevicePort, linkSpeed, duplex

        Raises:
            OmadaApiError: If fetching uplink info fails

        """
        if not device_macs:
            return []

        await self._ensure_valid_token()

        endpoint = f"/openapi/v1/{self._omada_id}/sites/{site_id}/devices/uplink-info"
        url = f"{self._api_url}{endpoint}"

        headers = {
            "Authorization": f"AccessToken={self._access_token}",
            "Content-Type": "application/json",
        }

        # Request body with device MACs (note: field name is "deviceMacs" not "macs")
        body = {"deviceMacs": device_macs}

        _LOGGER.debug(
            "Fetching uplink info for %d devices from %s", len(device_macs), url
        )

        try:
            async with self._session.post(
                url,
                headers=headers,
                json=body,
                timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
            ) as response:
                if response.status != 200:
                    response_text = await response.text()
                    _LOGGER.error("HTTP error %s: %s", response.status, response_text)
                    response.raise_for_status()

                result = await response.json()

                # Check for API error codes
                if result.get("errorCode") != 0:
                    error_msg = result.get("msg", "Unknown error")
                    raise OmadaApiError(f"API error: {error_msg}")

                return result["result"]  # type: ignore[no-any-return]

        except aiohttp.ClientError as err:
            raise OmadaApiError(f"Connection error: {err}") from err

    async def get_clients(
        self, site_id: str, page: int = 1, page_size: int = 100
    ) -> dict[str, Any]:
        """Get all clients for a site.

        Args:
            site_id: Site ID to get clients for
            page: Page number (starts at 1)
            page_size: Number of clients per page (1-1000)

        Returns:
            Dictionary with client data including totalRows, currentPage, and data list

        """
        await self._ensure_valid_token()

        endpoint = f"/openapi/v2/{self._omada_id}/sites/{site_id}/clients"
        url = f"{self._api_url}{endpoint}"

        headers = {
            "Authorization": f"AccessToken={self._access_token}",
            "Content-Type": "application/json",
        }

        # Request body for client query
        body = {
            "page": page,
            "pageSize": page_size,
            "scope": 0,  # 0: all clients, 1: online, 2: offline, 3: blocked
            "filters": {},
        }

        try:
            async with self._session.post(
                url,
                headers=headers,
                json=body,
                timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
            ) as response:
                if response.status != 200:
                    response_text = await response.text()
                    _LOGGER.error("HTTP error %s: %s", response.status, response_text)
                    response.raise_for_status()

                result = await response.json()

                # Check for API error codes
                if result.get("errorCode") != 0:
                    error_msg = result.get("msg", "Unknown error")
                    raise OmadaApiError(f"API error: {error_msg}")

                return result["result"]  # type: ignore[no-any-return]

        except aiohttp.ClientError as err:
            raise OmadaApiError(f"Connection error: {err}") from err

    async def get_applications(
        self, site_id: str, page: int = 1, page_size: int = 1000
    ) -> dict[str, Any]:
        """Get all available applications for DPI tracking.

        Args:
            site_id: Site ID to get applications for
            page: Page number (starts at 1)
            page_size: Number of applications per page (1-1000)

        Returns:
            Dictionary with application data including totalRows, currentPage, and data list
            Each app has: applicationId, applicationName, description, family

        """
        await self._ensure_valid_token()

        endpoint = f"/openapi/v1/{self._omada_id}/sites/{site_id}/applicationControl/applications"
        url = f"{self._api_url}{endpoint}"

        params = {
            "page": page,
            "pageSize": page_size,
        }

        headers = {
            "Authorization": f"AccessToken={self._access_token}",
            "Content-Type": "application/json",
        }

        try:
            async with self._session.get(
                url,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
            ) as response:
                if response.status != 200:
                    response_text = await response.text()
                    _LOGGER.error("HTTP error %s: %s", response.status, response_text)
                    response.raise_for_status()

                result = await response.json()

                # Check for API error codes
                if result.get("errorCode") != 0:
                    error_msg = result.get("msg", "Unknown error")
                    raise OmadaApiError(f"API error: {error_msg}")

                return result["result"]  # type: ignore[no-any-return]

        except aiohttp.ClientError as err:
            raise OmadaApiError(f"Connection error: {err}") from err

    async def get_client_app_traffic(
        self, site_id: str, client_mac: str, start: int, end: int
    ) -> list[dict[str, Any]]:
        """Get application traffic data for a specific client.

        Args:
            site_id: Site ID
            client_mac: Client MAC address
            start: Start timestamp in seconds (Unix timestamp)
            end: End timestamp in seconds (Unix timestamp)

        Returns:
            List of application traffic data, each with:
            applicationId, applicationName, upload, download, traffic, etc.

        """
        await self._ensure_valid_token()

        endpoint = f"/openapi/v1/{self._omada_id}/sites/{site_id}/dashboard/specificClientInfo/{client_mac}"
        url = f"{self._api_url}{endpoint}"

        params = {
            "start": start,
            "end": end,
        }

        headers = {
            "Authorization": f"AccessToken={self._access_token}",
            "Content-Type": "application/json",
        }

        try:
            async with self._session.get(
                url,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
            ) as response:
                if response.status != 200:
                    response_text = await response.text()
                    _LOGGER.error("HTTP error %s: %s", response.status, response_text)
                    response.raise_for_status()

                result = await response.json()

                # Check for API error codes
                if result.get("errorCode") != 0:
                    error_msg = result.get("msg", "Unknown error")
                    raise OmadaApiError(f"API error: {error_msg}")

                return result.get("result", [])  # type: ignore[no-any-return]

        except aiohttp.ClientError as err:
            raise OmadaApiError(f"Connection error: {err}") from err

    @property
    def access_token(self) -> str:
        """Get current access token."""
        return self._access_token

    @property
    def refresh_token(self) -> str:
        """Get current refresh token."""
        return self._refresh_token

    @property
    def token_expires_at(self) -> dt.datetime:
        """Get token expiration time."""
        return self._token_expires_at


class OmadaApiError(Exception):
    """General API exception."""


class OmadaApiAuthError(OmadaApiError):
    """Authentication exception."""
