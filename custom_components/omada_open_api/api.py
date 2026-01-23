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

                return result["result"]["data"]

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
