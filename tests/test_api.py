"""Tests for Omada Open API client token management."""

import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
from homeassistant.core import HomeAssistant
import pytest

from custom_components.omada_open_api.api import OmadaApiClient, OmadaApiError
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

    api_client = OmadaApiClient(
        hass,
        mock_config_entry,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=expires_at,
    )

    with (
        patch("aiohttp.ClientSession.post") as mock_post,
        patch.object(hass.config_entries, "async_update_entry") as mock_update,
    ):
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
        mock_update.assert_called_once()
        updated_data = mock_update.call_args[1]["data"]
        assert updated_data[CONF_ACCESS_TOKEN] == "new_access_token"
        assert updated_data[CONF_REFRESH_TOKEN] == "new_refresh_token"


async def test_refresh_token_expiry_triggers_renewal(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test that error -44114 triggers automatic fresh token request."""
    # Set token to expire soon to trigger refresh attempt
    expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=2)
    mock_config_entry.data[CONF_TOKEN_EXPIRES_AT] = expires_at.isoformat()

    api_client = OmadaApiClient(
        hass,
        mock_config_entry,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=expires_at,
    )

    with (
        patch("aiohttp.ClientSession.post") as mock_post,
        patch.object(hass.config_entries, "async_update_entry") as mock_update,
    ):
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
        mock_update.assert_called()
        updated_data = mock_update.call_args[1]["data"]
        assert updated_data[CONF_ACCESS_TOKEN] == "fresh_access_token"
        assert updated_data[CONF_REFRESH_TOKEN] == "fresh_refresh_token"


async def test_token_persistence_to_config_entry(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test that tokens are persisted to config entry after refresh."""
    # Set token to expire in 3 minutes (triggers refresh)
    expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=3)
    mock_config_entry.data[CONF_TOKEN_EXPIRES_AT] = expires_at.isoformat()

    api_client = OmadaApiClient(
        hass,
        mock_config_entry,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=expires_at,
    )

    with (
        patch("aiohttp.ClientSession.post") as mock_post,
        patch.object(hass.config_entries, "async_update_entry") as mock_update,
    ):
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
        mock_update.assert_called_once()
        updated_data = mock_update.call_args[1]["data"]
        assert updated_data[CONF_ACCESS_TOKEN] == "persisted_access_token"
        assert updated_data[CONF_REFRESH_TOKEN] == "persisted_refresh_token"
        assert CONF_TOKEN_EXPIRES_AT in updated_data

        # Verify the expiry time is set correctly (should be ~2 hours from now)
        expiry_time = dt.datetime.fromisoformat(updated_data[CONF_TOKEN_EXPIRES_AT])
        time_until_expiry = expiry_time - dt.datetime.now(dt.UTC)
        # Should be between 1.9 and 2.0 hours (7200 seconds = 2 hours)
        assert (
            dt.timedelta(hours=1, minutes=54)
            < time_until_expiry
            < dt.timedelta(hours=2)
        )


async def test_authenticated_request_retries_on_token_expired(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test that _authenticated_request retries when API returns -44112 (token expired)."""
    expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)
    mock_config_entry.data[CONF_TOKEN_EXPIRES_AT] = expires_at.isoformat()

    api_client = OmadaApiClient(
        hass,
        mock_config_entry,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=expires_at,
    )

    with (
        patch.object(api_client._session, "get") as mock_get,  # noqa: SLF001
        patch.object(
            api_client, "_refresh_access_token", new_callable=AsyncMock
        ) as mock_refresh,
        patch.object(hass.config_entries, "async_update_entry"),
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

    api_client = OmadaApiClient(
        hass,
        mock_config_entry,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=expires_at,
    )

    with (
        patch.object(api_client._session, "get") as mock_get,  # noqa: SLF001
        patch.object(
            api_client, "_refresh_access_token", new_callable=AsyncMock
        ) as mock_refresh,
        patch.object(hass.config_entries, "async_update_entry"),
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

    api_client = OmadaApiClient(
        hass,
        mock_config_entry,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=expires_at,
    )

    with (
        patch.object(api_client._session, "get") as mock_get,  # noqa: SLF001
        patch.object(
            api_client, "_refresh_access_token", new_callable=AsyncMock
        ) as mock_refresh,
        patch.object(hass.config_entries, "async_update_entry"),
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

    api_client = OmadaApiClient(
        hass,
        mock_config_entry,
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=expires_at,
    )

    with (
        patch("aiohttp.ClientSession.post") as mock_post,
        patch.object(hass.config_entries, "async_update_entry"),
    ):
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


# ---------------------------------------------------------------------------
# API method tests (get_sites, get_devices, get_clients, etc.)
# ---------------------------------------------------------------------------


async def test_get_sites(hass: HomeAssistant, mock_config_entry) -> None:
    """Test get_sites returns site list from API response."""
    api_client = OmadaApiClient(
        hass,
        mock_config_entry,
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

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_get.return_value.__aenter__.return_value = mock_response
        result = await api_client.get_sites()

    assert result == sites
    call_url = mock_get.call_args[0][0]
    assert "/openapi/v1/test_omada_id/sites" in call_url


async def test_get_devices(hass: HomeAssistant, mock_config_entry) -> None:
    """Test get_devices sends correct URL with site_id."""
    api_client = OmadaApiClient(
        hass,
        mock_config_entry,
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

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_get.return_value.__aenter__.return_value = mock_response
        result = await api_client.get_devices("site_001")

    assert result == devices
    call_url = mock_get.call_args[0][0]
    assert "/sites/site_001/devices" in call_url


async def test_get_clients(hass: HomeAssistant, mock_config_entry) -> None:
    """Test get_clients uses POST with correct body."""
    api_client = OmadaApiClient(
        hass,
        mock_config_entry,
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

    with patch("aiohttp.ClientSession.post") as mock_post:
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
    api_client = OmadaApiClient(
        hass,
        mock_config_entry,
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

    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_post.return_value.__aenter__.return_value = mock_response
        result = await api_client.get_device_uplink_info(
            "site_001", ["AA-BB-CC-DD-EE-01"]
        )

    assert result == uplink_data
    body = mock_post.call_args[1]["json"]
    assert body["deviceMacs"] == ["AA-BB-CC-DD-EE-01"]


async def test_get_device_uplink_info_empty_list(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test get_device_uplink_info with empty MAC list returns early."""
    api_client = OmadaApiClient(
        hass,
        mock_config_entry,
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
    api_client = OmadaApiClient(
        hass,
        mock_config_entry,
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

    with patch("aiohttp.ClientSession.get") as mock_get:
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
    api_client = OmadaApiClient(
        hass,
        mock_config_entry,
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

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_get.return_value.__aenter__.return_value = mock_response
        with pytest.raises(OmadaApiError, match="HTTP 500"):
            await api_client.get_sites()


async def test_authenticated_request_api_error_code(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test that non-zero API errorCode raises OmadaApiError."""
    api_client = OmadaApiClient(
        hass,
        mock_config_entry,
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

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_get.return_value.__aenter__.return_value = mock_response
        with pytest.raises(OmadaApiError, match="Permission denied"):
            await api_client.get_sites()


# ---------------------------------------------------------------------------
# get_switch_ports_poe tests
# ---------------------------------------------------------------------------


async def test_get_switch_ports_poe_single_page(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test get_switch_ports_poe fetches a single page of PoE data."""
    api_client = OmadaApiClient(
        hass,
        mock_config_entry,
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

    with patch("aiohttp.ClientSession.get") as mock_get:
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
    api_client = OmadaApiClient(
        hass,
        mock_config_entry,
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

    with patch("aiohttp.ClientSession.get") as mock_get:
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
    api_client = OmadaApiClient(
        hass,
        mock_config_entry,
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

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_get.return_value.__aenter__.return_value = mock_response
        result = await api_client.get_switch_ports_poe("site_001")

    assert result == []


async def test_get_poe_usage(hass: HomeAssistant, mock_config_entry) -> None:
    """Test get_poe_usage returns per-switch PoE budget data."""
    api_client = OmadaApiClient(
        hass,
        mock_config_entry,
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

    with patch("aiohttp.ClientSession.get") as mock_get:
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
    api_client = OmadaApiClient(
        hass,
        mock_config_entry,
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

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_get.return_value.__aenter__.return_value = mock_response
        result = await api_client.get_poe_usage("site_001")

    assert result == []


# ---------------------------------------------------------------------------
# get_device_client_stats
# ---------------------------------------------------------------------------


async def test_get_device_client_stats(hass: HomeAssistant, mock_config_entry) -> None:
    """Test get_device_client_stats sends correct POST payload."""
    api_client = OmadaApiClient(
        hass,
        mock_config_entry,
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

    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_post.return_value.__aenter__.return_value = mock_response
        result = await api_client.get_device_client_stats(
            "site_001", ["AA-BB-CC-DD-EE-01"]
        )

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
    api_client = OmadaApiClient(
        hass,
        mock_config_entry,
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
    api_client = OmadaApiClient(
        hass,
        mock_config_entry,
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

    with patch("aiohttp.ClientSession.put") as mock_put:
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
    api_client = OmadaApiClient(
        hass,
        mock_config_entry,
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

    with patch("aiohttp.ClientSession.put") as mock_put:
        mock_put.return_value.__aenter__.return_value = mock_response
        await api_client.set_port_profile_override(
            "site_001", "AA-BB-CC-DD-EE-02", 3, enable=False
        )

    assert mock_put.call_args[1]["json"] == {"profileOverrideEnable": False}


async def test_set_port_poe_mode_on(hass: HomeAssistant, mock_config_entry) -> None:
    """Test set_port_poe_mode with poe_enabled=True sends poeMode 1."""
    api_client = OmadaApiClient(
        hass,
        mock_config_entry,
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

    with patch("aiohttp.ClientSession.put") as mock_put:
        mock_put.return_value.__aenter__.return_value = mock_response
        await api_client.set_port_poe_mode(
            "site_001", "AA-BB-CC-DD-EE-02", 1, poe_enabled=True
        )

    call_url = mock_put.call_args[0][0]
    assert "/switches/AA-BB-CC-DD-EE-02/ports/1/poe-mode" in call_url
    assert mock_put.call_args[1]["json"] == {"poeMode": 1}


async def test_set_port_poe_mode_off(hass: HomeAssistant, mock_config_entry) -> None:
    """Test set_port_poe_mode with poe_enabled=False sends poeMode 0."""
    api_client = OmadaApiClient(
        hass,
        mock_config_entry,
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

    with patch("aiohttp.ClientSession.put") as mock_put:
        mock_put.return_value.__aenter__.return_value = mock_response
        await api_client.set_port_poe_mode(
            "site_001", "AA-BB-CC-DD-EE-02", 1, poe_enabled=False
        )

    assert mock_put.call_args[1]["json"] == {"poeMode": 0}
