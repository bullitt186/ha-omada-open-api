"""Authentication strategies for Omada API."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
import datetime as dt
import logging
from typing import TYPE_CHECKING

import aiohttp

from .const import DEFAULT_TIMEOUT, TOKEN_EXPIRY_BUFFER

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_LOGGER = logging.getLogger(__name__)


class OmadaAuthStrategy(ABC):
    """Abstract base for Omada authentication strategies."""

    @abstractmethod
    async def authenticate(self) -> None:
        """Perform initial authentication."""

    @abstractmethod
    async def ensure_valid_session(self) -> None:
        """Ensure session is valid, refreshing if needed."""

    @abstractmethod
    def decorate_request(self, headers: dict[str, str]) -> dict[str, str]:
        """Add auth headers to a request."""

    @abstractmethod
    async def handle_auth_failure(self) -> None:
        """Handle an authentication failure by re-authenticating."""


class ClientCredentialsAuth(OmadaAuthStrategy):
    """Standard OpenAPI client_credentials OAuth flow."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        token_update_callback: Callable[[str, str, str], Awaitable[None]],
        api_url: str,
        omada_id: str,
        client_id: str,
        client_secret: str,
        access_token: str,
        refresh_token: str,
        token_expires_at: dt.datetime,
    ) -> None:
        """Initialize with OAuth credentials and current tokens."""
        self._session = session
        self._token_update_callback = token_update_callback
        self._api_url = api_url.rstrip("/")
        self._omada_id = omada_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._token_expires_at = token_expires_at
        self._lock = asyncio.Lock()

    @property
    def access_token(self) -> str:
        """Return current access token."""
        return self._access_token

    @property
    def refresh_token(self) -> str:
        """Return current refresh token."""
        return self._refresh_token

    @property
    def token_expires_at(self) -> dt.datetime:
        """Return token expiration time."""
        return self._token_expires_at

    async def authenticate(self) -> None:
        """Get fresh tokens via client_credentials grant."""
        await self._get_fresh_tokens()

    async def ensure_valid_session(self) -> None:
        """Refresh access token if near expiry."""
        async with self._lock:
            now = dt.datetime.now(dt.UTC)
            buffer = dt.timedelta(seconds=TOKEN_EXPIRY_BUFFER)
            if now >= self._token_expires_at - buffer:
                _LOGGER.debug("Access token expired or expiring soon, refreshing")
                await self._refresh_access_token()

    def decorate_request(self, headers: dict[str, str]) -> dict[str, str]:
        """Add AccessToken authorization header."""
        headers["Authorization"] = f"AccessToken={self._access_token}"
        return headers

    async def handle_auth_failure(self) -> None:
        """Refresh token on auth failure."""
        async with self._lock:
            await self._refresh_access_token()

    async def _refresh_access_token(self) -> None:
        """Refresh via refresh_token grant, falling back to client_credentials."""
        from .api import OmadaApiAuthError, OmadaApiError

        url = f"{self._api_url}/openapi/authorize/token"
        params = {
            "grant_type": "refresh_token",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "refresh_token": self._refresh_token,
        }

        try:
            async with self._session.post(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
            ) as response:
                if response.status == 401:
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
                    if error_code in (-44114, -44111, -44106):
                        _LOGGER.info(
                            "Token refresh failed (error %s: %s), falling back "
                            "to client_credentials grant",
                            error_code,
                            result.get("msg", ""),
                        )
                        await self._get_fresh_tokens()
                        return

                    raise OmadaApiAuthError(
                        f"Token refresh failed: {result.get('msg', '')} "
                        f"(code: {error_code})"
                    )

                token_data = result["result"]
                self._access_token = token_data["accessToken"]
                self._refresh_token = token_data["refreshToken"]
                self._token_expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(
                    seconds=token_data["expiresIn"]
                )
                await self._persist_tokens()

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

    async def _get_fresh_tokens(self) -> None:
        """Get fresh tokens via client_credentials grant."""
        from .api import OmadaApiAuthError

        url = f"{self._api_url}/openapi/authorize/token"
        params = {"grant_type": "client_credentials"}
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
                    raise OmadaApiAuthError(
                        f"API error: {result.get('msg', 'Unknown error')}"
                    )

                token_data = result["result"]
                self._access_token = token_data["accessToken"]
                self._refresh_token = token_data["refreshToken"]
                self._token_expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(
                    seconds=token_data["expiresIn"]
                )
                await self._persist_tokens()

        except aiohttp.ClientError as err:
            raise OmadaApiAuthError(
                f"Connection error getting fresh tokens: {err}"
            ) from err

    async def _persist_tokens(self) -> None:
        """Persist tokens via callback."""
        await self._token_update_callback(
            self._access_token,
            self._refresh_token,
            self._token_expires_at.isoformat(),
        )


class WebSessionAuth(OmadaAuthStrategy):
    """Fusion Gateway web-session authentication."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        token_update_callback: Callable[..., Awaitable[None]],
        api_url: str,
        omada_id: str,
        username: str,
        password: str,
    ) -> None:
        """Initialize with web login credentials."""
        self._session = session
        self._token_update_callback = token_update_callback
        self._api_url = api_url.rstrip("/")
        self._omada_id = omada_id
        self._username = username
        self._password = password
        self._csrf_token: str | None = None
        self._lock = asyncio.Lock()

    async def authenticate(self) -> None:
        """Perform web login to get CSRF token."""
        from .api import OmadaApiAuthError

        url = f"{self._api_url}/{self._omada_id}/api/v2/login"
        data = {"username": self._username, "password": self._password}

        try:
            async with self._session.post(
                url,
                json=data,
                timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
            ) as response:
                result = await response.json()
                if result.get("errorCode") != 0:
                    raise OmadaApiAuthError(
                        f"Login failed: {result.get('msg', 'Unknown error')}"
                    )
                self._csrf_token = result["result"]["token"]
        except aiohttp.ClientError as err:
            raise OmadaApiAuthError(f"Connection error during login: {err}") from err

    async def ensure_valid_session(self) -> None:
        """Login if no CSRF token is present."""
        if self._csrf_token is not None:
            return
        async with self._lock:
            if self._csrf_token is None:
                await self.authenticate()

    def decorate_request(self, headers: dict[str, str]) -> dict[str, str]:
        """Add Fusion-specific CSRF and request source headers."""
        headers["Csrf-Token"] = self._csrf_token or ""
        headers["Omada-Request-Source"] = "web-local"
        return headers

    async def handle_auth_failure(self) -> None:
        """Clear CSRF token and re-login."""
        self._csrf_token = None
        await self.authenticate()
