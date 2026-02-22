"""Tests for Omada Open API client token management."""

import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
from homeassistant.core import HomeAssistant
import pytest

from custom_components.omada_open_api.api import (
    OmadaApiAuthError,
    OmadaApiClient,
    OmadaApiError,
)
from custom_components.omada_open_api.const import (
    CONF_ACCESS_TOKEN,
    CONF_API_URL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_OMADA_ID,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN_EXPIRES_AT,
)


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry for testing."""
    entry = MagicMock()
    entry.data = {
        CONF_API_URL: "https://test-controller.example.com",
        CONF_OMADA_ID: "test_omada_id",
        CONF_CLIENT_ID: "test_client_id",
        CONF_CLIENT_SECRET: "test_client_secret",
        CONF_ACCESS_TOKEN: "old_access_token",
        CONF_REFRESH_TOKEN: "old_refresh_token",
        CONF_TOKEN_EXPIRES_AT: (
            dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)
        ).isoformat(),
    }
    entry.entry_id = "test_entry_id"
    return entry


async def test_token_refresh_before_expiry(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test that tokens are refreshed automatically before expiry (5-min buffer)."""
    # Set token to expire in 4 minutes (within 5-minute refresh buffer)
    expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=4)
    mock_config_entry.data[CONF_TOKEN_EXPIRES_AT] = expires_at.isoformat()

    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=expires_at,
    )

    mock_post = mock_session.post
    # Mock successful token refresh response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {
        "errorCode": 0,
        "msg": "Success",
        "result": {
            "accessToken": "new_access_token",
            "tokenType": "bearer",
            "expiresIn": 7200,
            "refreshToken": "new_refresh_token",
        },
    }
    mock_post.return_value.__aenter__.return_value = mock_response

    # Call method that should trigger token refresh
    await api_client._ensure_valid_token()  # noqa: SLF001

    # Verify refresh endpoint was called
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert "/openapi/authorize/token" in call_args[0][0]
    assert call_args[1]["params"]["grant_type"] == "refresh_token"

    # Verify refresh_token grant puts ALL params in query string (no body)
    refresh_params = call_args[1]["params"]
    assert refresh_params["client_id"] == "test_client_id"
    assert refresh_params["client_secret"] == "test_client_secret"
    assert refresh_params["refresh_token"] == "old_refresh_token"
    assert "json" not in call_args[1]  # No body for refresh_token grant

    # Verify config entry was updated
    mock_callback.assert_called_once()
    cb_args = mock_callback.call_args[0]
    assert cb_args[0] == "new_access_token"
    assert cb_args[1] == "new_refresh_token"


async def test_refresh_token_expiry_triggers_renewal(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test that error -44114 triggers automatic fresh token request."""
    # Set token to expire soon to trigger refresh attempt
    expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=2)
    mock_config_entry.data[CONF_TOKEN_EXPIRES_AT] = expires_at.isoformat()

    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=expires_at,
    )

    mock_post = mock_session.post
    # First call: refresh returns error -44114 (refresh token expired)
    # Second call: get fresh tokens succeeds
    refresh_response = AsyncMock()
    refresh_response.status = 200
    refresh_response.json.return_value = {
        "errorCode": -44114,
        "msg": "Refresh token expired",
    }

    fresh_token_response = AsyncMock()
    fresh_token_response.status = 200
    fresh_token_response.json.return_value = {
        "errorCode": 0,
        "msg": "Success",
        "result": {
            "accessToken": "fresh_access_token",
            "tokenType": "bearer",
            "expiresIn": 7200,
            "refreshToken": "fresh_refresh_token",
        },
    }

    mock_post.return_value.__aenter__.side_effect = [
        refresh_response,
        fresh_token_response,
    ]

    # Call method that should trigger refresh, then renewal
    await api_client._ensure_valid_token()  # noqa: SLF001

    # Verify both calls were made
    assert mock_post.call_count == 2

    # First call should be refresh_token grant
    first_call = mock_post.call_args_list[0]
    assert first_call[1]["params"]["grant_type"] == "refresh_token"

    # Second call should be client_credentials grant
    second_call = mock_post.call_args_list[1]
    assert second_call[1]["params"]["grant_type"] == "client_credentials"
    # client_credentials puts omadacId, client_id, client_secret in body
    cred_body = second_call[1]["json"]
    assert cred_body["omadacId"] == "test_omada_id"
    assert cred_body["client_id"] == "test_client_id"
    assert cred_body["client_secret"] == "test_client_secret"

    # Verify config entry was updated with fresh tokens
    mock_callback.assert_called()
    cb_args = mock_callback.call_args[0]
    assert cb_args[0] == "fresh_access_token"
    assert cb_args[1] == "fresh_refresh_token"


async def test_token_persistence_to_config_entry(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test that tokens are persisted to config entry after refresh."""
    # Set token to expire in 3 minutes (triggers refresh)
    expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=3)
    mock_config_entry.data[CONF_TOKEN_EXPIRES_AT] = expires_at.isoformat()

    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=expires_at,
    )

    mock_post = mock_session.post
    # Mock successful token refresh
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {
        "errorCode": 0,
        "msg": "Success",
        "result": {
            "accessToken": "persisted_access_token",
            "tokenType": "bearer",
            "expiresIn": 7200,
            "refreshToken": "persisted_refresh_token",
        },
    }
    mock_post.return_value.__aenter__.return_value = mock_response

    # Trigger token refresh
    await api_client._ensure_valid_token()  # noqa: SLF001

    # Verify config entry was updated
    mock_callback.assert_called_once()
    cb_args = mock_callback.call_args[0]
    assert cb_args[0] == "persisted_access_token"
    assert cb_args[1] == "persisted_refresh_token"
    # cb_args[2] is the ISO expiry string

    # Verify the expiry time is set correctly (should be ~2 hours from now)
    expiry_time = dt.datetime.fromisoformat(cb_args[2])
    time_until_expiry = expiry_time - dt.datetime.now(dt.UTC)
    # Should be between 1.9 and 2.0 hours (7200 seconds = 2 hours)
    assert dt.timedelta(hours=1, minutes=54) < time_until_expiry < dt.timedelta(hours=2)


async def test_authenticated_request_retries_on_token_expired(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test that _authenticated_request retries when API returns -44112 (token expired)."""
    expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)
    mock_config_entry.data[CONF_TOKEN_EXPIRES_AT] = expires_at.isoformat()

    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=expires_at,
    )

    mock_get = mock_session.get
    with (
        patch.object(
            api_client, "_refresh_access_token", new_callable=AsyncMock
        ) as mock_refresh,
    ):
        # First call returns -44112 (token expired), second call succeeds
        expired_response = AsyncMock()
        expired_response.status = 200
        expired_response.json.return_value = {
            "errorCode": -44112,
            "msg": "The access token has expired",
        }

        success_response = AsyncMock()
        success_response.status = 200
        success_response.json.return_value = {
            "errorCode": 0,
            "msg": "Success",
            "result": {"data": [{"siteId": "site1"}]},
        }

        mock_get.return_value.__aenter__.side_effect = [
            expired_response,
            success_response,
        ]

        # Make the refresh update the token so retry works
        async def update_token() -> None:
            api_client._access_token = "refreshed_token"  # noqa: SLF001

        mock_refresh.side_effect = update_token

        result = await api_client._authenticated_request(  # noqa: SLF001
            "get",
            "https://test-controller.example.com/openapi/v1/test/sites",
            params={"pageSize": 100, "page": 1},
        )

        # Verify refresh was called
        mock_refresh.assert_called_once()

        # Verify second request succeeded
        assert result["result"]["data"][0]["siteId"] == "site1"
        assert mock_get.call_count == 2


async def test_authenticated_request_retries_on_token_invalid(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test that _authenticated_request retries on -44113 (token invalid)."""
    expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)
    mock_config_entry.data[CONF_TOKEN_EXPIRES_AT] = expires_at.isoformat()

    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=expires_at,
    )

    mock_get = mock_session.get
    with (
        patch.object(
            api_client, "_refresh_access_token", new_callable=AsyncMock
        ) as mock_refresh,
    ):
        # First call returns -44113, second succeeds
        invalid_response = AsyncMock()
        invalid_response.status = 200
        invalid_response.json.return_value = {
            "errorCode": -44113,
            "msg": "The access token is Invalid",
        }

        success_response = AsyncMock()
        success_response.status = 200
        success_response.json.return_value = {
            "errorCode": 0,
            "msg": "Success",
            "result": {"data": []},
        }

        mock_get.return_value.__aenter__.side_effect = [
            invalid_response,
            success_response,
        ]

        result = await api_client._authenticated_request(  # noqa: SLF001
            "get",
            "https://test-controller.example.com/openapi/v1/test/sites",
        )

        mock_refresh.assert_called_once()
        assert result["errorCode"] == 0


async def test_authenticated_request_retries_on_http_401(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test that _authenticated_request retries on HTTP 401."""
    expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)
    mock_config_entry.data[CONF_TOKEN_EXPIRES_AT] = expires_at.isoformat()

    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=expires_at,
    )

    mock_get = mock_session.get
    with (
        patch.object(
            api_client, "_refresh_access_token", new_callable=AsyncMock
        ) as mock_refresh,
    ):
        # First call returns HTTP 401, second succeeds
        unauthorized_response = AsyncMock()
        unauthorized_response.status = 401

        success_response = AsyncMock()
        success_response.status = 200
        success_response.json.return_value = {
            "errorCode": 0,
            "msg": "Success",
            "result": {"data": []},
        }

        mock_get.return_value.__aenter__.side_effect = [
            unauthorized_response,
            success_response,
        ]

        result = await api_client._authenticated_request(  # noqa: SLF001
            "get",
            "https://test-controller.example.com/openapi/v1/test/sites",
        )

        mock_refresh.assert_called_once()
        assert result["errorCode"] == 0


async def test_refresh_connection_error_falls_back_to_client_credentials(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test that connection error during refresh falls back to client_credentials."""
    expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=2)
    mock_config_entry.data[CONF_TOKEN_EXPIRES_AT] = expires_at.isoformat()

    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=expires_at,
    )

    mock_post = mock_session.post
    # First call: refresh raises connection error
    # Second call: client_credentials succeeds
    fresh_token_response = AsyncMock()
    fresh_token_response.status = 200
    fresh_token_response.json.return_value = {
        "errorCode": 0,
        "msg": "Success",
        "result": {
            "accessToken": "fresh_access_token",
            "tokenType": "bearer",
            "expiresIn": 7200,
            "refreshToken": "fresh_refresh_token",
        },
    }

    # Side effects: first raises error, second succeeds
    mock_post.return_value.__aenter__.side_effect = [
        aiohttp.ClientError("Connection refused"),
        fresh_token_response,
    ]

    await api_client._ensure_valid_token()  # noqa: SLF001

    # Verify both calls were made (refresh + client_credentials)
    assert mock_post.call_count == 2

    # Second call should be client_credentials
    second_call = mock_post.call_args_list[1]
    assert second_call[1]["params"]["grant_type"] == "client_credentials"


async def test_get_fresh_tokens_http_error(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test _get_fresh_tokens raises on non-200 HTTP status."""
    expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(hours=2)
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=expires_at,
    )
    mock_response = AsyncMock()
    mock_response.status = 500
    mock_session.post.return_value.__aenter__.return_value = mock_response

    with pytest.raises(OmadaApiAuthError, match="status 500"):
        await api_client._get_fresh_tokens()  # noqa: SLF001


async def test_get_fresh_tokens_api_error(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test _get_fresh_tokens raises on API error code."""
    expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(hours=2)
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=expires_at,
    )
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {
        "errorCode": -30001,
        "msg": "Invalid credentials",
    }
    mock_session.post.return_value.__aenter__.return_value = mock_response

    with pytest.raises(OmadaApiAuthError, match="Invalid credentials"):
        await api_client._get_fresh_tokens()  # noqa: SLF001


async def test_get_fresh_tokens_connection_error(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test _get_fresh_tokens raises on connection error."""
    expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(hours=2)
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=expires_at,
    )
    mock_session.post.return_value.__aenter__.side_effect = aiohttp.ClientError(
        "timeout"
    )

    with pytest.raises(OmadaApiAuthError, match="Connection error"):
        await api_client._get_fresh_tokens()  # noqa: SLF001


async def test_refresh_non_200_falls_back(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test _refresh_access_token falls back to client_credentials on non-200."""
    expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(hours=2)
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=expires_at,
    )
    # First call: refresh returns 503, second call: client_credentials succeeds
    error_response = AsyncMock()
    error_response.status = 503
    success_response = AsyncMock()
    success_response.status = 200
    success_response.json.return_value = {
        "errorCode": 0,
        "result": {
            "accessToken": "new_token",
            "tokenType": "bearer",
            "expiresIn": 7200,
            "refreshToken": "new_refresh",
        },
    }
    mock_session.post.return_value.__aenter__.side_effect = [
        error_response,
        success_response,
    ]

    await api_client._refresh_access_token()  # noqa: SLF001
    assert mock_session.post.call_count == 2


async def test_refresh_unknown_api_error_raises(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test _refresh_access_token raises on unknown API error code."""
    expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(hours=2)
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=expires_at,
    )
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {
        "errorCode": -99999,
        "msg": "Unknown server error",
    }
    mock_session.post.return_value.__aenter__.return_value = mock_response

    with pytest.raises(OmadaApiAuthError, match="Unknown server error"):
        await api_client._refresh_access_token()  # noqa: SLF001


async def test_authenticated_request_401_after_retry(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test _authenticated_request raises after 401 on retry attempt."""
    expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(hours=2)
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=expires_at,
    )

    # Both attempts return 401
    response_401 = AsyncMock()
    response_401.status = 401
    response_401.text.return_value = "Unauthorized"

    # Refresh succeeds but second request also returns 401
    refresh_response = AsyncMock()
    refresh_response.status = 200
    refresh_response.json.return_value = {
        "errorCode": 0,
        "result": {
            "accessToken": "new_token",
            "tokenType": "bearer",
            "expiresIn": 7200,
            "refreshToken": "new_refresh",
        },
    }

    mock_session.get.return_value.__aenter__.return_value = response_401
    mock_session.post.return_value.__aenter__.return_value = refresh_response

    with pytest.raises(OmadaApiError, match="HTTP 401 after token refresh"):
        await api_client._authenticated_request("get", "https://example.com/api")  # noqa: SLF001


async def test_authenticated_request_connection_error(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test _authenticated_request raises on connection error."""
    expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(hours=2)
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=expires_at,
    )
    mock_session.get.return_value.__aenter__.side_effect = aiohttp.ClientError(
        "Connection refused"
    )

    with pytest.raises(OmadaApiError, match="Connection error"):
        await api_client._authenticated_request("get", "https://example.com/api")  # noqa: SLF001


# ---------------------------------------------------------------------------
# API method tests (get_sites, get_devices, get_clients, etc.)
# ---------------------------------------------------------------------------


async def test_get_sites(hass: HomeAssistant, mock_config_entry) -> None:
    """Test get_sites returns site list from API response."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    sites = [{"siteId": "site_1", "name": "Office"}]
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {
        "errorCode": 0,
        "result": {"data": sites, "totalRows": 1},
    }

    mock_get = mock_session.get
    mock_get.return_value.__aenter__.return_value = mock_response
    result = await api_client.get_sites()

    assert result == sites
    call_url = mock_get.call_args[0][0]
    assert "/openapi/v1/test_omada_id/sites" in call_url


async def test_get_devices(hass: HomeAssistant, mock_config_entry) -> None:
    """Test get_devices sends correct URL with site_id."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    devices = [{"mac": "AA-BB-CC-DD-EE-01", "name": "AP", "type": "ap"}]
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {
        "errorCode": 0,
        "result": {"data": devices, "totalRows": 1},
    }

    mock_get = mock_session.get
    mock_get.return_value.__aenter__.return_value = mock_response
    result = await api_client.get_devices("site_001")

    assert result == devices
    call_url = mock_get.call_args[0][0]
    assert "/sites/site_001/devices" in call_url


async def test_get_clients(hass: HomeAssistant, mock_config_entry) -> None:
    """Test get_clients uses POST with correct body."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    clients_data = {"data": [{"mac": "11:22:33:44:55:AA"}], "totalRows": 1}
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {
        "errorCode": 0,
        "result": clients_data,
    }

    mock_post = mock_session.post
    mock_post.return_value.__aenter__.return_value = mock_response
    result = await api_client.get_clients("site_001", page=1, page_size=500)

    assert result == clients_data
    call_url = mock_post.call_args[0][0]
    assert "/sites/site_001/clients" in call_url

    # Verify POST body contains pagination.
    call_kwargs = mock_post.call_args[1]
    body = call_kwargs["json"]
    assert body["page"] == 1
    assert body["pageSize"] == 500


async def test_get_device_uplink_info(hass: HomeAssistant, mock_config_entry) -> None:
    """Test get_device_uplink_info sends MAC list in POST body."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    uplink_data = [{"deviceMac": "AA-BB-CC-DD-EE-01", "linkSpeed": 3}]
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {"errorCode": 0, "result": uplink_data}

    mock_post = mock_session.post
    mock_post.return_value.__aenter__.return_value = mock_response
    result = await api_client.get_device_uplink_info("site_001", ["AA-BB-CC-DD-EE-01"])

    assert result == uplink_data
    body = mock_post.call_args[1]["json"]
    assert body["deviceMacs"] == ["AA-BB-CC-DD-EE-01"]


async def test_get_device_uplink_info_empty_list(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test get_device_uplink_info with empty MAC list returns early."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    result = await api_client.get_device_uplink_info("site_001", [])
    assert result == []


async def test_get_client_app_traffic(hass: HomeAssistant, mock_config_entry) -> None:
    """Test get_client_app_traffic passes time range parameters."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    app_data = [{"applicationId": 100, "upload": 1024, "download": 2048}]
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {"errorCode": 0, "result": app_data}

    mock_get = mock_session.get
    mock_get.return_value.__aenter__.return_value = mock_response
    result = await api_client.get_client_app_traffic(
        "site_001", "AA:BB:CC:DD:EE:FF", 1000000, 2000000
    )

    assert result == app_data
    call_url = mock_get.call_args[0][0]
    assert "/specificClientInfo/AA:BB:CC:DD:EE:FF" in call_url
    call_params = mock_get.call_args[1]["params"]
    assert call_params["start"] == 1000000
    assert call_params["end"] == 2000000


async def test_authenticated_request_non_200_raises(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test that non-200 HTTP status raises OmadaApiError."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    mock_response = AsyncMock()
    mock_response.status = 500
    mock_response.text.return_value = "Internal Server Error"

    mock_get = mock_session.get
    mock_get.return_value.__aenter__.return_value = mock_response
    with pytest.raises(OmadaApiError, match="HTTP 500"):
        await api_client.get_sites()


async def test_authenticated_request_api_error_code(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test that non-zero API errorCode raises OmadaApiError."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {
        "errorCode": -30001,
        "msg": "Permission denied",
    }

    mock_get = mock_session.get
    mock_get.return_value.__aenter__.return_value = mock_response
    with pytest.raises(OmadaApiError, match="Permission denied"):
        await api_client.get_sites()


async def test_authenticated_request_api_error_code_attribute(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test OmadaApiError includes error_code attribute from API response."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {
        "errorCode": -1007,
        "msg": "No permission",
    }

    mock_get = mock_session.get
    mock_get.return_value.__aenter__.return_value = mock_response
    with pytest.raises(OmadaApiError) as exc_info:
        await api_client.get_sites()
    assert exc_info.value.error_code == -1007


async def test_omada_api_error_default_error_code() -> None:
    """Test OmadaApiError defaults error_code to None."""
    err = OmadaApiError("generic error")
    assert err.error_code is None


# ---------------------------------------------------------------------------
# get_switch_ports_poe tests
# ---------------------------------------------------------------------------


async def test_get_switch_ports_poe_single_page(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test get_switch_ports_poe fetches a single page of PoE data."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    poe_ports = [
        {"port": 1, "switchMac": "AA-BB", "power": 12.5, "supportPoe": True},
        {"port": 2, "switchMac": "AA-BB", "power": 0.0, "supportPoe": True},
    ]
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {
        "errorCode": 0,
        "result": {"data": poe_ports, "totalRows": 2},
    }

    mock_get = mock_session.get
    mock_get.return_value.__aenter__.return_value = mock_response
    result = await api_client.get_switch_ports_poe("site_001")

    assert len(result) == 2
    assert result[0]["power"] == 12.5
    call_url = mock_get.call_args[0][0]
    assert "/sites/site_001/switches/ports/poe-info" in call_url
    call_params = mock_get.call_args[1]["params"]
    assert call_params["page"] == 1
    assert call_params["pageSize"] == 1000


async def test_get_switch_ports_poe_multi_page(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test get_switch_ports_poe paginates across multiple pages."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    # Page 1: 1000 items, Page 2: 500 items (total 1500)
    page1_ports = [{"port": i, "switchMac": "AA"} for i in range(1000)]
    page2_ports = [{"port": i, "switchMac": "AA"} for i in range(1000, 1500)]

    page1_response = AsyncMock()
    page1_response.status = 200
    page1_response.json.return_value = {
        "errorCode": 0,
        "result": {"data": page1_ports, "totalRows": 1500},
    }

    page2_response = AsyncMock()
    page2_response.status = 200
    page2_response.json.return_value = {
        "errorCode": 0,
        "result": {"data": page2_ports, "totalRows": 1500},
    }

    mock_get = mock_session.get
    mock_get.return_value.__aenter__.side_effect = [
        page1_response,
        page2_response,
    ]
    result = await api_client.get_switch_ports_poe("site_001")

    assert len(result) == 1500
    assert mock_get.call_count == 2

    # First call page=1, second call page=2
    first_params = mock_get.call_args_list[0][1]["params"]
    assert first_params["page"] == 1
    second_params = mock_get.call_args_list[1][1]["params"]
    assert second_params["page"] == 2


async def test_get_switch_ports_poe_empty(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test get_switch_ports_poe with no PoE ports returns empty list."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {
        "errorCode": 0,
        "result": {"data": [], "totalRows": 0},
    }

    mock_get = mock_session.get
    mock_get.return_value.__aenter__.return_value = mock_response
    result = await api_client.get_switch_ports_poe("site_001")

    assert result == []


async def test_get_poe_usage(hass: HomeAssistant, mock_config_entry) -> None:
    """Test get_poe_usage returns per-switch PoE budget data."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    poe_usage_data = [
        {
            "mac": "AA-BB-CC-DD-EE-02",
            "name": "Switch-PoE-24",
            "portNum": 24,
            "totalPowerUsed": 45,
            "totalPercentUsed": 18.75,
            "totalPower": 240,
            "poePorts": [],
        }
    ]

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {
        "errorCode": 0,
        "result": poe_usage_data,
    }

    mock_get = mock_session.get
    mock_get.return_value.__aenter__.return_value = mock_response
    result = await api_client.get_poe_usage("site_001")

    assert len(result) == 1
    assert result[0]["mac"] == "AA-BB-CC-DD-EE-02"
    assert result[0]["totalPower"] == 240
    assert result[0]["totalPowerUsed"] == 45
    assert result[0]["totalPercentUsed"] == 18.75

    # Verify URL construction
    call_url = mock_get.call_args[0][0]
    assert "/dashboard/poe-usage" in call_url
    assert "test_omada_id" in call_url
    assert "site_001" in call_url


async def test_get_poe_usage_empty(hass: HomeAssistant, mock_config_entry) -> None:
    """Test get_poe_usage with no PoE switches returns empty list."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {
        "errorCode": 0,
        "result": [],
    }

    mock_get = mock_session.get
    mock_get.return_value.__aenter__.return_value = mock_response
    result = await api_client.get_poe_usage("site_001")

    assert result == []


# ---------------------------------------------------------------------------
# get_device_client_stats
# ---------------------------------------------------------------------------


async def test_get_device_client_stats(hass: HomeAssistant, mock_config_entry) -> None:
    """Test get_device_client_stats sends correct POST payload."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    stats = [
        {
            "mac": "AA-BB-CC-DD-EE-01",
            "clientNum": 15,
            "clientNum2g": 5,
            "clientNum5g": 8,
            "clientNum5g2": 0,
            "clientNum6g": 2,
        }
    ]
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {
        "errorCode": 0,
        "result": stats,
    }

    mock_post = mock_session.post
    mock_post.return_value.__aenter__.return_value = mock_response
    result = await api_client.get_device_client_stats("site_001", ["AA-BB-CC-DD-EE-01"])

    assert result == stats

    call_url = mock_post.call_args[0][0]
    assert "/clients/stat/devices" in call_url
    assert "test_omada_id" in call_url

    call_kwargs = mock_post.call_args[1]
    assert call_kwargs["json"] == {
        "devices": [{"mac": "AA-BB-CC-DD-EE-01", "siteId": "site_001"}]
    }


async def test_get_device_client_stats_empty_macs(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test get_device_client_stats returns empty list for no MACs."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    result = await api_client.get_device_client_stats("site_001", [])
    assert result == []


async def test_set_port_profile_override(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test set_port_profile_override sends correct PUT request."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {"errorCode": 0}

    mock_put = mock_session.put
    mock_put.return_value.__aenter__.return_value = mock_response
    await api_client.set_port_profile_override(
        "site_001", "AA-BB-CC-DD-EE-02", 1, enable=True
    )

    call_url = mock_put.call_args[0][0]
    assert "/switches/AA-BB-CC-DD-EE-02/ports/1/profile-override" in call_url
    assert mock_put.call_args[1]["json"] == {"profileOverrideEnable": True}


async def test_set_port_profile_override_disable(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test set_port_profile_override with enable=False."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {"errorCode": 0}

    mock_put = mock_session.put
    mock_put.return_value.__aenter__.return_value = mock_response
    await api_client.set_port_profile_override(
        "site_001", "AA-BB-CC-DD-EE-02", 3, enable=False
    )

    assert mock_put.call_args[1]["json"] == {"profileOverrideEnable": False}


async def test_set_port_poe_mode_on(hass: HomeAssistant, mock_config_entry) -> None:
    """Test set_port_poe_mode with poe_enabled=True sends poeMode 1."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {"errorCode": 0}

    mock_put = mock_session.put
    mock_put.return_value.__aenter__.return_value = mock_response
    await api_client.set_port_poe_mode(
        "site_001", "AA-BB-CC-DD-EE-02", 1, poe_enabled=True
    )

    call_url = mock_put.call_args[0][0]
    assert "/switches/AA-BB-CC-DD-EE-02/ports/1/poe-mode" in call_url
    assert mock_put.call_args[1]["json"] == {"poeMode": 1}


async def test_set_port_poe_mode_off(hass: HomeAssistant, mock_config_entry) -> None:
    """Test set_port_poe_mode with poe_enabled=False sends poeMode 0."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {"errorCode": 0}

    mock_put = mock_session.put
    mock_put.return_value.__aenter__.return_value = mock_response
    await api_client.set_port_poe_mode(
        "site_001", "AA-BB-CC-DD-EE-02", 1, poe_enabled=False
    )

    assert mock_put.call_args[1]["json"] == {"poeMode": 0}


async def test_reboot_device(hass: HomeAssistant, mock_config_entry) -> None:
    """Test reboot_device sends POST to correct endpoint."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {"errorCode": 0}

    mock_post = mock_session.post
    mock_post.return_value.__aenter__.return_value = mock_response
    await api_client.reboot_device("site_001", "AA-BB-CC-DD-EE-01")

    call_url = mock_post.call_args[0][0]
    assert "/devices/AA-BB-CC-DD-EE-01/reboot" in call_url
    assert "test_omada_id" in call_url


async def test_reconnect_client(hass: HomeAssistant, mock_config_entry) -> None:
    """Test reconnect_client sends POST to correct endpoint."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {"errorCode": 0}

    mock_post = mock_session.post
    mock_post.return_value.__aenter__.return_value = mock_response
    await api_client.reconnect_client("site_001", "11-22-33-44-55-AA")

    call_url = mock_post.call_args[0][0]
    assert "/clients/11-22-33-44-55-AA/reconnect" in call_url


async def test_start_wlan_optimization(hass: HomeAssistant, mock_config_entry) -> None:
    """Test start_wlan_optimization sends POST with strategy payload."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {"errorCode": 0, "result": {}}

    mock_post = mock_session.post
    mock_post.return_value.__aenter__.return_value = mock_response
    await api_client.start_wlan_optimization("site_001")

    call_url = mock_post.call_args[0][0]
    assert "/cmd/rfPlanning/rrmOptimization" in call_url
    assert mock_post.call_args[1]["json"] == {"optimizationStrategy": 0}


async def test_block_client(hass: HomeAssistant, mock_config_entry) -> None:
    """Test block_client sends POST to correct endpoint."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {"errorCode": 0}

    mock_post = mock_session.post
    mock_post.return_value.__aenter__.return_value = mock_response
    await api_client.block_client("site_001", "11-22-33-44-55-AA")

    call_url = mock_post.call_args[0][0]
    assert "/clients/11-22-33-44-55-AA/block" in call_url


async def test_unblock_client(hass: HomeAssistant, mock_config_entry) -> None:
    """Test unblock_client sends POST to correct endpoint."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {"errorCode": 0}

    mock_post = mock_session.post
    mock_post.return_value.__aenter__.return_value = mock_response
    await api_client.unblock_client("site_001", "11-22-33-44-55-AA")

    call_url = mock_post.call_args[0][0]
    assert "/clients/11-22-33-44-55-AA/unblock" in call_url


async def test_get_firmware_info(hass: HomeAssistant, mock_config_entry) -> None:
    """Test get_firmware_info sends GET to correct endpoint."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {
        "errorCode": 0,
        "result": {"curFwVer": "1.0", "lastFwVer": "1.1", "fwReleaseLog": "Fix"},
    }

    mock_get = mock_session.get
    mock_get.return_value.__aenter__.return_value = mock_response
    result = await api_client.get_firmware_info("site_001", "AA-BB-CC-DD-EE-01")

    call_url = mock_get.call_args[0][0]
    assert "/devices/AA-BB-CC-DD-EE-01/latest-firmware-info" in call_url
    assert result.get("curFwVer") == "1.0"


async def test_start_online_upgrade(hass: HomeAssistant, mock_config_entry) -> None:
    """Test start_online_upgrade sends POST to correct endpoint."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {"errorCode": 0}

    mock_post = mock_session.post
    mock_post.return_value.__aenter__.return_value = mock_response
    await api_client.start_online_upgrade("site_001", "AA-BB-CC-DD-EE-01")

    call_url = mock_post.call_args[0][0]
    assert "/devices/AA-BB-CC-DD-EE-01/start-online-upgrade" in call_url


async def test_get_led_setting(hass: HomeAssistant, mock_config_entry) -> None:
    """Test get_led_setting sends GET to correct endpoint."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {
        "errorCode": 0,
        "result": {"enable": True},
    }

    mock_get = mock_session.get
    mock_get.return_value.__aenter__.return_value = mock_response
    result = await api_client.get_led_setting("site_001")

    call_url = mock_get.call_args[0][0]
    assert "/sites/site_001/led" in call_url
    assert result.get("enable") is True


async def test_set_led_setting(hass: HomeAssistant, mock_config_entry) -> None:
    """Test set_led_setting sends PUT with enable payload."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {"errorCode": 0}

    mock_put = mock_session.put
    mock_put.return_value.__aenter__.return_value = mock_response
    await api_client.set_led_setting("site_001", enable=False)

    call_url = mock_put.call_args[0][0]
    assert "/sites/site_001/led" in call_url
    assert mock_put.call_args[1]["json"] == {"enable": False}


async def test_locate_device(hass: HomeAssistant, mock_config_entry) -> None:
    """Test locate_device sends POST with locateEnable payload."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {"errorCode": 0}

    mock_post = mock_session.post
    mock_post.return_value.__aenter__.return_value = mock_response
    await api_client.locate_device("site_001", "AA-BB-CC-DD-EE-01", enable=True)

    call_url = mock_post.call_args[0][0]
    assert "/devices/AA-BB-CC-DD-EE-01/locate" in call_url
    assert mock_post.call_args[1]["json"] == {"locateEnable": True}


async def test_get_ap_radios(hass: HomeAssistant, mock_config_entry) -> None:
    """Test get_ap_radios sends GET to correct endpoint."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {
        "errorCode": 0,
        "result": {"radioTraffic2g": {"tx": 100, "rx": 200}},
    }

    mock_get = mock_session.get
    mock_get.return_value.__aenter__.return_value = mock_response
    result = await api_client.get_ap_radios("site_001", "AA-BB-CC-DD-EE-01")

    call_url = mock_get.call_args[0][0]
    assert "/aps/AA-BB-CC-DD-EE-01/radios" in call_url
    assert "radioTraffic2g" in result


# ---------------------------------------------------------------------------
# check_write_access tests
# ---------------------------------------------------------------------------


async def test_check_write_access_success(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test check_write_access returns True when write probe succeeds."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    get_response = AsyncMock()
    get_response.status = 200
    get_response.json.return_value = {
        "errorCode": 0,
        "result": {"enable": True},
    }

    put_response = AsyncMock()
    put_response.status = 200
    put_response.json.return_value = {"errorCode": 0, "result": {}}

    mock_get = mock_session.get
    mock_put = mock_session.put
    if True:
        mock_get.return_value.__aenter__.return_value = get_response
        mock_put.return_value.__aenter__.return_value = put_response
        result = await api_client.check_write_access("site_001")

    assert result is True
    # The PUT should write back the same LED state that was read.
    put_data = mock_put.call_args[1]["json"]
    assert put_data == {"enable": True}


async def test_check_write_access_viewer_only(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test check_write_access returns False on permissions error."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    get_response = AsyncMock()
    get_response.status = 200
    get_response.json.return_value = {
        "errorCode": 0,
        "result": {"enable": True},
    }

    put_response = AsyncMock()
    put_response.status = 200
    put_response.json.return_value = {
        "errorCode": -1007,
        "msg": "No permission",
    }

    mock_get = mock_session.get
    mock_put = mock_session.put
    if True:
        mock_get.return_value.__aenter__.return_value = get_response
        mock_put.return_value.__aenter__.return_value = put_response
        result = await api_client.check_write_access("site_001")

    assert result is False


# ---------------------------------------------------------------------------
# New API methods tests (gateway_info, SSIDs)
# ---------------------------------------------------------------------------


async def test_get_gateway_info(hass: HomeAssistant, mock_config_entry) -> None:
    """Test get_gateway_info fetches gateway information with temperature."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {
        "errorCode": 0,
        "result": {
            "mac": "AA-BB-CC-DD-EE-01",
            "ip": "192.168.1.1",
            "temp": 45,
            "cpuUtil": 25,
            "memUtil": 40,
            "uptime": "123456",
        },
    }

    mock_get = mock_session.get
    mock_get.return_value.__aenter__.return_value = mock_response
    result = await api_client.get_gateway_info("site_001", "AA-BB-CC-DD-EE-01")

    call_url = mock_get.call_args[0][0]
    assert "/gateways/AA-BB-CC-DD-EE-01" in call_url
    assert result["temp"] == 45
    assert result["mac"] == "AA-BB-CC-DD-EE-01"


async def test_get_site_ssids(hass: HomeAssistant, mock_config_entry) -> None:
    """Test get_site_ssids fetches SSID list for a site."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    # Match actual Omada API response structure
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {
        "errorCode": 0,
        "msg": "Success.",
        "result": [
            {
                "wlanId": "wlan_001",
                "wlanName": "Default",
                "ssidList": [
                    {
                        "ssidId": "ssid_001",
                        "ssidName": "HomeWiFi",
                    },
                    {
                        "ssidId": "ssid_002",
                        "ssidName": "GuestWiFi",
                    },
                ],
            }
        ],
    }

    mock_get = mock_session.get
    mock_get.return_value.__aenter__.return_value = mock_response
    result = await api_client.get_site_ssids("site_001")

    call_url = mock_get.call_args[0][0]
    assert "/wireless-network/ssids" in call_url
    assert "type=3" in call_url  # Verify type parameter is included
    assert len(result) == 2
    assert result[0]["ssidName"] == "HomeWiFi"
    assert result[0]["wlanId"] == "wlan_001"
    assert result[0]["wlanName"] == "Default"
    assert result[1]["ssidName"] == "GuestWiFi"


async def test_get_site_ssids_comprehensive(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test get_site_ssids_comprehensive fetches all SSIDs from all WLAN groups."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    # Mock WLAN groups response
    wlan_groups_response = AsyncMock()
    wlan_groups_response.status = 200
    wlan_groups_response.json.return_value = {
        "errorCode": 0,
        "msg": "Success.",
        "result": [
            {"wlanId": "wlan_001", "name": "Default"},
            {"wlanId": "wlan_002", "name": "Guest"},
        ],
    }

    # Mock SSID list responses for each WLAN
    ssids_wlan1_response = AsyncMock()
    ssids_wlan1_response.status = 200
    ssids_wlan1_response.json.return_value = {
        "errorCode": 0,
        "msg": "Success.",
        "result": {
            "totalRows": 3,
            "currentPage": 1,
            "currentSize": 3,
            "data": [
                {"ssidId": "ssid_001", "name": "HomeWiFi", "broadcast": True},
                {"ssidId": "ssid_002", "name": "GuestWiFi", "broadcast": True},
                {"ssidId": "ssid_003", "name": "IoT", "broadcast": True},
            ],
        },
    }

    ssids_wlan2_response = AsyncMock()
    ssids_wlan2_response.status = 200
    ssids_wlan2_response.json.return_value = {
        "errorCode": 0,
        "msg": "Success.",
        "result": {
            "totalRows": 2,
            "currentPage": 1,
            "currentSize": 2,
            "data": [
                {"ssidId": "ssid_004", "name": "Cameras", "broadcast": False},
                {"ssidId": "ssid_005", "name": "Kids", "broadcast": True},
            ],
        },
    }

    mock_get = mock_session.get
    if True:
        # First call returns WLAN groups, then SSIDs for each WLAN
        mock_get.return_value.__aenter__.side_effect = [
            wlan_groups_response,
            ssids_wlan1_response,
            ssids_wlan2_response,
        ]

        result = await api_client.get_site_ssids_comprehensive("site_001")

    # Verify WLAN groups call
    first_call_url = mock_get.call_args_list[0][0][0]
    assert "/wireless-network/wlans" in first_call_url
    assert "/ssids" not in first_call_url

    # Verify SSID list calls for each WLAN
    second_call_url = mock_get.call_args_list[1][0][0]
    assert "/wireless-network/wlans/wlan_001/ssids" in second_call_url
    assert mock_get.call_args_list[1][1]["params"]["page"] == 1
    assert mock_get.call_args_list[1][1]["params"]["pageSize"] == 100

    third_call_url = mock_get.call_args_list[2][0][0]
    assert "/wireless-network/wlans/wlan_002/ssids" in third_call_url

    # Verify result contains all SSIDs from both WLANs with normalized field names
    assert len(result) == 5
    assert result[0]["ssidName"] == "HomeWiFi"
    assert result[0]["wlanId"] == "wlan_001"
    assert result[0]["wlanName"] == "Default"
    assert result[3]["ssidName"] == "Cameras"
    assert result[3]["wlanId"] == "wlan_002"
    assert result[3]["wlanName"] == "Guest"
    assert result[4]["ssidName"] == "Kids"


async def test_get_site_ssids_comprehensive_pagination(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test get_site_ssids_comprehensive handles pagination correctly."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    # Mock WLAN groups response
    wlan_groups_response = AsyncMock()
    wlan_groups_response.status = 200
    wlan_groups_response.json.return_value = {
        "errorCode": 0,
        "msg": "Success.",
        "result": [{"wlanId": "wlan_001", "name": "Default"}],
    }

    # Mock paginated SSID responses (simulate 150 total items with pageSize=100)
    page1_response = AsyncMock()
    page1_response.status = 200
    page1_data = [
        {"ssidId": f"ssid_{i:03d}", "name": f"WiFi_{i:03d}", "broadcast": True}
        for i in range(100)
    ]
    page1_response.json.return_value = {
        "errorCode": 0,
        "msg": "Success.",
        "result": {
            "totalRows": 150,
            "currentPage": 1,
            "currentSize": 100,
            "data": page1_data,
        },
    }

    page2_response = AsyncMock()
    page2_response.status = 200
    page2_data = [
        {"ssidId": f"ssid_{i:03d}", "name": f"WiFi_{i:03d}", "broadcast": True}
        for i in range(100, 150)
    ]
    page2_response.json.return_value = {
        "errorCode": 0,
        "msg": "Success.",
        "result": {
            "totalRows": 150,
            "currentPage": 2,
            "currentSize": 50,
            "data": page2_data,
        },
    }

    mock_get = mock_session.get
    mock_get.return_value.__aenter__.side_effect = [
        wlan_groups_response,
        page1_response,
        page2_response,
    ]

    result = await api_client.get_site_ssids_comprehensive("site_001")

    # Verify pagination calls
    assert mock_get.call_count == 3  # 1 WLAN groups + 2 SSID pages
    assert mock_get.call_args_list[1][1]["params"]["page"] == 1
    assert mock_get.call_args_list[2][1]["params"]["page"] == 2

    # Verify all items returned with field normalization
    assert len(result) == 150
    assert result[0]["ssidName"] == "WiFi_000"
    assert result[99]["ssidName"] == "WiFi_099"
    assert result[149]["ssidName"] == "WiFi_149"
    assert all(ssid["wlanId"] == "wlan_001" for ssid in result)
    assert all(ssid["wlanName"] == "Default" for ssid in result)


async def test_get_ssid_detail(hass: HomeAssistant, mock_config_entry) -> None:
    """Test get_ssid_detail fetches detailed SSID configuration."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {
        "errorCode": 0,
        "result": {
            "id": "ssid_001",
            "wlanId": "wlan_001",
            "name": "HomeWiFi",
            "broadcast": True,
            "band": 7,
            "security": 4,
        },
    }

    mock_get = mock_session.get
    mock_get.return_value.__aenter__.return_value = mock_response
    result = await api_client.get_ssid_detail("site_001", "wlan_001", "ssid_001")

    call_url = mock_get.call_args[0][0]
    assert "/wireless-network/wlans/wlan_001/ssids/ssid_001" in call_url
    assert result["name"] == "HomeWiFi"
    assert result["band"] == 7


async def test_update_ssid_basic_config(hass: HomeAssistant, mock_config_entry) -> None:
    """Test update_ssid_basic_config updates SSID configuration."""
    mock_session = MagicMock()
    mock_callback = AsyncMock()
    api_client = OmadaApiClient(
        session=mock_session,
        token_update_callback=mock_callback,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {"errorCode": 0, "result": {}}

    config = {"name": "HomeWiFi", "band": 7, "broadcast": False}

    mock_patch = mock_session.patch
    mock_patch.return_value.__aenter__.return_value = mock_response
    await api_client.update_ssid_basic_config(
        "site_001", "wlan_001", "ssid_001", config
    )

    call_url = mock_patch.call_args[0][0]
    assert (
        "/wireless-network/wlans/wlan_001/ssids/ssid_001/update-basic-config"
        in call_url
    )
    assert mock_patch.call_args[1]["json"] == config
