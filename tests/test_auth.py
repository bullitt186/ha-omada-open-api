"""Tests for Omada auth strategies."""

from __future__ import annotations

import asyncio
import datetime as dt
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.omada_open_api.auth import (
    ClientCredentialsAuth,
    OmadaAuthStrategy,
    WebSessionAuth,
)

from .conftest import TEST_API_URL, TEST_CLIENT_ID, TEST_CLIENT_SECRET, TEST_OMADA_ID

TEST_USERNAME = "admin"
TEST_PASSWORD = "secret123"


# ---------------------------------------------------------------------------
# ClientCredentialsAuth
# ---------------------------------------------------------------------------


class TestClientCredentialsAuth:
    """Tests for the ClientCredentialsAuth strategy."""

    def _make_auth(
        self,
        *,
        token_expires_at: dt.datetime | None = None,
    ) -> ClientCredentialsAuth:
        """Create a ClientCredentialsAuth with test defaults."""
        session = MagicMock(spec=aiohttp.ClientSession)
        callback = AsyncMock()
        expires = token_expires_at or (dt.datetime.now(dt.UTC) + dt.timedelta(hours=1))
        return ClientCredentialsAuth(
            session=session,
            token_update_callback=callback,
            api_url=TEST_API_URL,
            omada_id=TEST_OMADA_ID,
            client_id=TEST_CLIENT_ID,
            client_secret=TEST_CLIENT_SECRET,
            access_token="test_token",
            refresh_token="test_refresh",
            token_expires_at=expires,
        )

    def test_is_auth_strategy(self) -> None:
        """ClientCredentialsAuth is an OmadaAuthStrategy."""
        auth = self._make_auth()
        assert isinstance(auth, OmadaAuthStrategy)

    def test_decorate_request_adds_access_token_header(self) -> None:
        """decorate_request sets Authorization: AccessToken=... header."""
        auth = self._make_auth()
        headers: dict[str, str] = {}
        result = auth.decorate_request(headers)
        assert result["Authorization"] == "AccessToken=test_token"

    @pytest.mark.asyncio
    async def test_ensure_valid_session_no_refresh_when_fresh(self) -> None:
        """No refresh attempt when token is not near expiry."""
        auth = self._make_auth(
            token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)
        )
        # Should not raise and should not trigger refresh
        await auth.ensure_valid_session()
        # Session.post should NOT have been called (no refresh needed)
        auth._session.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_valid_session_refreshes_when_expired(self) -> None:
        """Refresh triggered when token is past expiry buffer."""
        auth = self._make_auth(
            token_expires_at=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)
        )

        # Mock the refresh response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "errorCode": 0,
                "result": {
                    "accessToken": "new_access",
                    "refreshToken": "new_refresh",
                    "expiresIn": 7200,
                },
            }
        )
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        auth._session.post.return_value = mock_ctx

        await auth.ensure_valid_session()

        assert auth._access_token == "new_access"
        assert auth._refresh_token == "new_refresh"

    @pytest.mark.asyncio
    async def test_handle_auth_failure_refreshes_token(self) -> None:
        """handle_auth_failure triggers a token refresh."""
        auth = self._make_auth()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "errorCode": 0,
                "result": {
                    "accessToken": "refreshed_token",
                    "refreshToken": "refreshed_refresh",
                    "expiresIn": 7200,
                },
            }
        )
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        auth._session.post.return_value = mock_ctx

        await auth.handle_auth_failure()

        assert auth._access_token == "refreshed_token"

    @pytest.mark.asyncio
    async def test_refresh_falls_back_to_fresh_tokens_on_expired_refresh(
        self,
    ) -> None:
        """When refresh token is expired (-44114), falls back to client_credentials."""
        auth = self._make_auth(
            token_expires_at=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)
        )

        # First call: refresh_token grant returns -44114
        refresh_response = AsyncMock()
        refresh_response.status = 200
        refresh_response.json = AsyncMock(
            return_value={"errorCode": -44114, "msg": "Refresh token expired"}
        )

        # Second call: client_credentials grant succeeds
        fresh_response = AsyncMock()
        fresh_response.status = 200
        fresh_response.json = AsyncMock(
            return_value={
                "errorCode": 0,
                "result": {
                    "accessToken": "fresh_access",
                    "refreshToken": "fresh_refresh",
                    "expiresIn": 7200,
                },
            }
        )

        mock_ctx_1 = AsyncMock()
        mock_ctx_1.__aenter__ = AsyncMock(return_value=refresh_response)
        mock_ctx_1.__aexit__ = AsyncMock(return_value=False)

        mock_ctx_2 = AsyncMock()
        mock_ctx_2.__aenter__ = AsyncMock(return_value=fresh_response)
        mock_ctx_2.__aexit__ = AsyncMock(return_value=False)

        auth._session.post.side_effect = [mock_ctx_1, mock_ctx_2]

        await auth.ensure_valid_session()

        assert auth._access_token == "fresh_access"

    @pytest.mark.asyncio
    async def test_token_update_callback_called_after_refresh(self) -> None:
        """Token update callback is invoked after successful refresh."""
        auth = self._make_auth(
            token_expires_at=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)
        )

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "errorCode": 0,
                "result": {
                    "accessToken": "cb_token",
                    "refreshToken": "cb_refresh",
                    "expiresIn": 7200,
                },
            }
        )
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        auth._session.post.return_value = mock_ctx

        await auth.ensure_valid_session()

        auth._token_update_callback.assert_awaited_once()


# ---------------------------------------------------------------------------
# WebSessionAuth
# ---------------------------------------------------------------------------


class TestWebSessionAuth:
    """Tests for the WebSessionAuth strategy."""

    def _make_auth(self) -> WebSessionAuth:
        """Create a WebSessionAuth with test defaults."""
        session = MagicMock(spec=aiohttp.ClientSession)
        callback = AsyncMock()
        return WebSessionAuth(
            session=session,
            token_update_callback=callback,
            api_url=TEST_API_URL,
            omada_id=TEST_OMADA_ID,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

    def test_is_auth_strategy(self) -> None:
        """WebSessionAuth is an OmadaAuthStrategy."""
        auth = self._make_auth()
        assert isinstance(auth, OmadaAuthStrategy)

    @pytest.mark.asyncio
    async def test_authenticate_success(self) -> None:
        """Successful web login stores CSRF token."""
        auth = self._make_auth()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "errorCode": 0,
                "result": {"token": "csrf_token_123"},
            }
        )
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        auth._session.post.return_value = mock_ctx

        await auth.authenticate()

        assert auth._csrf_token == "csrf_token_123"
        # Verify correct URL was called
        call_args = auth._session.post.call_args
        url = call_args[0][0]
        assert f"/{TEST_OMADA_ID}/api/v2/login" in url

    @pytest.mark.asyncio
    async def test_authenticate_invalid_credentials(self) -> None:
        """Login failure raises OmadaApiAuthError."""
        from custom_components.omada_open_api.api import OmadaApiAuthError

        auth = self._make_auth()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "errorCode": -30109,
                "msg": "Invalid username or password",
            }
        )
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        auth._session.post.return_value = mock_ctx

        with pytest.raises(OmadaApiAuthError):
            await auth.authenticate()

    def test_decorate_request_adds_csrf_and_web_local(self) -> None:
        """decorate_request sets Csrf-Token and Omada-Request-Source headers."""
        auth = self._make_auth()
        auth._csrf_token = "my_csrf"

        headers: dict[str, str] = {}
        result = auth.decorate_request(headers)

        assert result["Csrf-Token"] == "my_csrf"
        assert result["Omada-Request-Source"] == "web-local"
        assert "Authorization" not in result

    @pytest.mark.asyncio
    async def test_ensure_valid_session_logs_in_when_no_token(self) -> None:
        """ensure_valid_session authenticates when CSRF token is missing."""
        auth = self._make_auth()
        assert auth._csrf_token is None

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "errorCode": 0,
                "result": {"token": "new_csrf"},
            }
        )
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        auth._session.post.return_value = mock_ctx

        await auth.ensure_valid_session()

        assert auth._csrf_token == "new_csrf"

    @pytest.mark.asyncio
    async def test_ensure_valid_session_skips_when_has_token(self) -> None:
        """ensure_valid_session does nothing when CSRF token already present."""
        auth = self._make_auth()
        auth._csrf_token = "existing_csrf"

        await auth.ensure_valid_session()

        auth._session.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_auth_failure_clears_and_relogins(self) -> None:
        """handle_auth_failure clears CSRF token and re-authenticates."""
        auth = self._make_auth()
        auth._csrf_token = "old_csrf"

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "errorCode": 0,
                "result": {"token": "relogin_csrf"},
            }
        )
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        auth._session.post.return_value = mock_ctx

        await auth.handle_auth_failure()

        assert auth._csrf_token == "relogin_csrf"

    @pytest.mark.asyncio
    async def test_concurrent_login_uses_lock(self) -> None:
        """Multiple concurrent ensure_valid_session calls only login once."""
        auth = self._make_auth()

        call_count = 0

        def _mock_post(*args: object, **kwargs: object) -> AsyncMock:
            nonlocal call_count
            call_count += 1
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value={
                    "errorCode": 0,
                    "result": {"token": "concurrent_csrf"},
                }
            )
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            return mock_ctx

        auth._session.post = _mock_post

        # Run 5 concurrent ensure_valid_session calls
        await asyncio.gather(
            auth.ensure_valid_session(),
            auth.ensure_valid_session(),
            auth.ensure_valid_session(),
            auth.ensure_valid_session(),
            auth.ensure_valid_session(),
        )

        # Only one login should have happened (lock prevents duplicates)
        assert call_count == 1
