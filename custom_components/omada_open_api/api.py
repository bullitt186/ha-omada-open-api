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

    async def _authenticated_request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated API request with automatic token renewal.

        Handles HTTP 401 and API error codes -44112 (token expired) and
        -44113 (token invalid) by refreshing the token and retrying once.

        Args:
            method: HTTP method ("get" or "post")
            url: Full URL to request
            params: Query parameters
            json_data: JSON body (for POST requests)

        Returns:
            Parsed JSON response dictionary

        Raises:
            OmadaApiError: If the request fails after retry

        """
        await self._ensure_valid_token()

        for attempt in range(2):
            headers = {
                "Authorization": f"AccessToken={self._access_token}",
                "Content-Type": "application/json",
            }

            try:
                request_kwargs: dict[str, Any] = {
                    "headers": headers,
                    "timeout": aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
                }
                if params:
                    request_kwargs["params"] = params
                if json_data is not None:
                    request_kwargs["json"] = json_data

                async with getattr(self._session, method)(
                    url, **request_kwargs
                ) as response:
                    if response.status == 401:
                        if attempt == 0:
                            _LOGGER.debug(
                                "HTTP 401 on API request, refreshing token and "
                                "retrying (attempt %s)",
                                attempt + 1,
                            )
                            async with self._token_refresh_lock:
                                await self._refresh_access_token()
                            continue
                        response_text = await response.text()
                        raise OmadaApiError(
                            f"HTTP 401 after token refresh: {response_text}"
                        )

                    if response.status != 200:
                        response_text = await response.text()
                        _LOGGER.error(
                            "HTTP error %s: %s", response.status, response_text
                        )
                        raise OmadaApiError(f"HTTP {response.status}: {response_text}")

                    result = await response.json()
                    error_code = result.get("errorCode")

                    # Token-related errors: refresh and retry
                    if error_code in (-44112, -44113):
                        if attempt == 0:
                            _LOGGER.info(
                                "API returned token error %s: %s, refreshing "
                                "token and retrying",
                                error_code,
                                result.get("msg", ""),
                            )
                            async with self._token_refresh_lock:
                                await self._refresh_access_token()
                            continue
                        raise OmadaApiError(
                            f"Token error {error_code} persists after refresh: "
                            f"{result.get('msg', '')}"
                        )

                    if error_code != 0:
                        error_msg = result.get("msg", "Unknown error")
                        raise OmadaApiError(f"API error {error_code}: {error_msg}")

                    return result  # type: ignore[no-any-return]

            except aiohttp.ClientError as err:
                raise OmadaApiError(f"Connection error: {err}") from err

        # Should not reach here, but just in case
        raise OmadaApiError("Request failed after all retry attempts")

    async def _get_fresh_tokens(self) -> None:
        """Get fresh tokens using client credentials grant.

        Per the Omada API docs, only grant_type goes in the query string.
        The omadacId, client_id, and client_secret go in the JSON body.

        Raises:
            OmadaApiAuthError: If getting fresh tokens fails

        """
        _LOGGER.info("Requesting fresh tokens using client_credentials grant")
        url = f"{self._api_url}/openapi/authorize/token"
        # Per API docs: only grant_type in query string
        params = {
            "grant_type": "client_credentials",
        }
        # Per API docs: omadacId, client_id, client_secret in JSON body
        data = {
            "omadacId": self._omada_id,
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

                _LOGGER.info(
                    "Fresh tokens obtained successfully, expires in %s seconds",
                    token_data["expiresIn"],
                )

                # Persist to config entry
                await self._update_config_entry()

        except aiohttp.ClientError as err:
            raise OmadaApiAuthError(
                f"Connection error getting fresh tokens: {err}"
            ) from err

    async def _refresh_access_token(self) -> None:
        """Refresh the access token using refresh token.

        Per the Omada API docs, refresh_token grant puts ALL parameters in the
        query string with no request body. Refresh tokens are single-use: after
        use, the old token is invalidated and a new one is returned.

        If refresh token is expired or invalid, automatically gets fresh tokens
        using client credentials.

        Raises:
            OmadaApiAuthError: If refresh fails

        """
        url = f"{self._api_url}/openapi/authorize/token"
        # Per API docs: all params go in query string for refresh_token grant
        params = {
            "grant_type": "refresh_token",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "refresh_token": self._refresh_token,
        }

        _LOGGER.debug("Attempting token refresh via refresh_token grant")

        try:
            async with self._session.post(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
            ) as response:
                if response.status == 401:
                    # Refresh token expired, get fresh tokens automatically
                    _LOGGER.info(
                        "HTTP 401 during token refresh, falling back to "
                        "client_credentials grant"
                    )
                    await self._get_fresh_tokens()
                    return

                if response.status != 200:
                    _LOGGER.warning(
                        "Token refresh returned HTTP %s, falling back to "
                        "client_credentials grant",
                        response.status,
                    )
                    await self._get_fresh_tokens()
                    return

                result = await response.json()
                error_code = result.get("errorCode")

                if error_code != 0:
                    error_msg = result.get("msg", "Unknown error")

                    # Error code -44114: Refresh token expired
                    # Error code -44111: Invalid grant type
                    # Error code -44106: Invalid client credentials
                    if error_code in (-44114, -44111, -44106):
                        _LOGGER.info(
                            "Token refresh failed (error %s: %s), falling back "
                            "to client_credentials grant",
                            error_code,
                            error_msg,
                        )
                        await self._get_fresh_tokens()
                        return

                    _LOGGER.error(
                        "API error during token refresh: %s - %s",
                        error_code,
                        error_msg,
                    )
                    raise OmadaApiAuthError(
                        f"Token refresh failed: {error_msg} (code: {error_code})"
                    )

                token_data = result["result"]
                self._access_token = token_data["accessToken"]
                self._refresh_token = token_data["refreshToken"]
                self._token_expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(
                    seconds=token_data["expiresIn"]
                )

                _LOGGER.debug(
                    "Access token refreshed successfully, expires in %s seconds",
                    token_data["expiresIn"],
                )

                # Persist to config entry
                await self._update_config_entry()

        except aiohttp.ClientError as err:
            _LOGGER.warning(
                "Connection error during token refresh: %s, falling back to "
                "client_credentials grant",
                err,
            )
            try:
                await self._get_fresh_tokens()
            except (OmadaApiError, aiohttp.ClientError) as fresh_err:
                raise OmadaApiError(
                    f"Token refresh failed and client_credentials fallback "
                    f"also failed: {fresh_err}"
                ) from err

    async def get_sites(self) -> list[dict[str, Any]]:
        """Get list of sites from Omada controller.

        Returns:
            List of site dictionaries

        Raises:
            OmadaApiError: If API request fails

        """
        url = f"{self._api_url}/openapi/v1/{self._omada_id}/sites"
        params = {"pageSize": 100, "page": 1}

        result = await self._authenticated_request("get", url, params=params)
        return result["result"]["data"]  # type: ignore[no-any-return]

    async def get_devices(self, site_id: str) -> list[dict[str, Any]]:
        """Fetch devices for a specific site.

        Args:
            site_id: The site ID to fetch devices for

        Returns:
            List of device dictionaries

        Raises:
            OmadaApiError: If fetching devices fails

        """
        url = f"{self._api_url}/openapi/v1/{self._omada_id}/sites/{site_id}/devices"
        params = {"pageSize": 100, "page": 1}

        _LOGGER.debug("Fetching devices from %s", url)

        result = await self._authenticated_request("get", url, params=params)
        return result["result"]["data"]  # type: ignore[no-any-return]

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

        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/devices/uplink-info"
        )

        _LOGGER.debug(
            "Fetching uplink info for %d devices from %s", len(device_macs), url
        )

        result = await self._authenticated_request(
            "post", url, json_data={"deviceMacs": device_macs}
        )
        return result["result"]  # type: ignore[no-any-return]

    async def get_clients(
        self, site_id: str, page: int = 1, page_size: int = 100
    ) -> dict[str, Any]:
        """Get all clients for a site.

        Args:
            site_id: Site ID to get clients for
            page: Page number (starts at 1)
            page_size: Number of clients per page (1-1000)

        Returns:
            Dictionary with client data including totalRows, currentPage,
            and data list

        """
        url = f"{self._api_url}/openapi/v2/{self._omada_id}/sites/{site_id}/clients"
        body = {
            "page": page,
            "pageSize": page_size,
            "scope": 0,  # 0: all clients, 1: online, 2: offline, 3: blocked
            "filters": {},
        }

        result = await self._authenticated_request("post", url, json_data=body)
        return result["result"]  # type: ignore[no-any-return]

    async def get_applications(
        self, site_id: str, page: int = 1, page_size: int = 1000
    ) -> dict[str, Any]:
        """Get all available applications for DPI tracking.

        Args:
            site_id: Site ID to get applications for
            page: Page number (starts at 1)
            page_size: Number of applications per page (1-1000)

        Returns:
            Dictionary with application data including totalRows, currentPage,
            and data list. Each app has: applicationId, applicationName,
            description, family

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/applicationControl/applications"
        )
        params = {"page": page, "pageSize": page_size}

        result = await self._authenticated_request("get", url, params=params)
        return result["result"]  # type: ignore[no-any-return]

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
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/dashboard/specificClientInfo/{client_mac}"
        )
        params = {"start": start, "end": end}

        result = await self._authenticated_request("get", url, params=params)
        return result.get("result", [])  # type: ignore[no-any-return]

    async def get_switch_ports_poe(self, site_id: str) -> list[dict[str, Any]]:
        """Get PoE information for all switch ports in a site.

        Fetches all pages of PoE port data in a single loop.

        Args:
            site_id: Site ID to get PoE port data for

        Returns:
            List of PoE port dictionaries, each containing port, switchMac,
            switchName, portName, supportPoe, poe, power, voltage, current,
            poeStatus, pdClass, poeDisplayType, connectedStatus, etc.

        Raises:
            OmadaApiError: If fetching PoE data fails

        """
        url = (
            f"{self._api_url}/openapi/v1/{self._omada_id}"
            f"/sites/{site_id}/switches/ports/poe-info"
        )
        page_size = 1000
        page = 1
        all_ports: list[dict[str, Any]] = []

        while True:
            params = {"page": page, "pageSize": page_size}
            result = await self._authenticated_request("get", url, params=params)
            data = result.get("result", {})
            ports = data.get("data", [])
            total_rows = data.get("totalRows", 0)
            all_ports.extend(ports)

            if len(all_ports) >= total_rows or len(ports) < page_size:
                break
            page += 1

        _LOGGER.debug(
            "Fetched %d PoE port records for site %s", len(all_ports), site_id
        )
        return all_ports

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
