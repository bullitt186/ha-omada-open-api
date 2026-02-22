"""Tests for Omada Open API config flow."""

import datetime as dt
from unittest.mock import AsyncMock, patch

import aiohttp
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.omada_open_api.config_flow import InvalidAuthError
from custom_components.omada_open_api.const import (
    CONF_ACCESS_TOKEN,
    CONF_API_URL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_CONTROLLER_TYPE,
    CONF_OMADA_ID,
    CONF_REFRESH_TOKEN,
    CONF_REGION,
    CONF_SELECTED_APPLICATIONS,
    CONF_SELECTED_CLIENTS,
    CONF_SELECTED_SITES,
    CONF_TOKEN_EXPIRES_AT,
    CONTROLLER_TYPE_CLOUD,
    CONTROLLER_TYPE_LOCAL,
    DOMAIN,
)


@pytest.fixture
def mock_setup_entry() -> AsyncMock:
    """Mock async_setup_entry."""
    with patch(
        "custom_components.omada_open_api.async_setup_entry",
        return_value=True,
    ) as mock_setup:
        yield mock_setup


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

MOCK_TOKEN_DATA = {
    "accessToken": "test_access_token",
    "tokenType": "bearer",
    "expiresIn": 7200,
    "refreshToken": "test_refresh_token",
}

MOCK_SITES = [{"siteId": "site123", "name": "Test Site"}]

MOCK_CLIENTS = [
    {
        "mac": "AA-BB-CC-DD-EE-01",
        "name": "Phone",
        "ip": "192.168.1.50",
        "active": True,
    },
]

MOCK_APPLICATIONS = [
    {
        "applicationId": 100,
        "application": "YouTube",
        "family": "Streaming",
    },
    {
        "applicationId": 200,
        "application": "Netflix",
        "family": "Streaming",
    },
]


def _future_token_expiry() -> str:
    """Return an ISO timestamp 1 hour in the future."""
    return (dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)).isoformat()


async def test_user_step_shows_controller_types(hass: HomeAssistant) -> None:
    """Test the user step shows controller type selection."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert CONF_CONTROLLER_TYPE in result["data_schema"].schema


async def test_cloud_controller_flow(hass: HomeAssistant) -> None:
    """Test cloud controller configuration flow."""
    # Start flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    # Select cloud controller
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_CONTROLLER_TYPE: CONTROLLER_TYPE_CLOUD},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "cloud"
    assert CONF_REGION in result["data_schema"].schema


async def test_local_controller_flow(hass: HomeAssistant) -> None:
    """Test local controller configuration flow."""
    # Start flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    # Select local controller
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_CONTROLLER_TYPE: CONTROLLER_TYPE_LOCAL},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "local"


async def test_credentials_step_invalid_auth(hass: HomeAssistant) -> None:
    """Test credentials step with invalid authentication."""
    # Start flow and select cloud controller
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_CONTROLLER_TYPE: CONTROLLER_TYPE_CLOUD},
    )

    # Select region
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_REGION: "us"},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "credentials"

    # Test with invalid credentials (should show error)
    with patch(
        "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_access_token",
        side_effect=Exception("Invalid credentials"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_OMADA_ID: "test_omada_id",
                CONF_CLIENT_ID: "test_client_id",
                CONF_CLIENT_SECRET: "test_client_secret",
            },
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "credentials"
        assert "base" in result["errors"]


async def test_connection_timeout_error(hass: HomeAssistant) -> None:
    """Test handling of connection timeout errors."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_CONTROLLER_TYPE: CONTROLLER_TYPE_LOCAL},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"api_url": "https://unreachable.local:8043"},
    )

    # Mock connection timeout
    with patch(
        "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_access_token",
        side_effect=TimeoutError("Connection timeout"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_OMADA_ID: "test_omada_id",
                CONF_CLIENT_ID: "test_client_id",
                CONF_CLIENT_SECRET: "test_client_secret",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "credentials"
    assert "base" in result["errors"]


async def test_invalid_client_credentials_error_code(hass: HomeAssistant) -> None:
    """Test handling of invalid client credentials (error code -44106)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_CONTROLLER_TYPE: CONTROLLER_TYPE_CLOUD},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_REGION: "us"},
    )

    # Mock API returning error code -44106
    mock_invalid_response = {
        "errorCode": -44106,
        "msg": "Invalid client credentials",
    }

    with patch(
        "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_access_token",
        return_value=mock_invalid_response,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_OMADA_ID: "test_omada_id",
                CONF_CLIENT_ID: "invalid_client_id",
                CONF_CLIENT_SECRET: "invalid_secret",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "credentials"
    assert "base" in result["errors"]


async def test_complete_cloud_flow_with_token_storage(hass: HomeAssistant) -> None:
    """Test complete cloud controller flow with token storage in config entry."""
    with (
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_access_token",
            return_value={
                "accessToken": "test_access_token",
                "tokenType": "bearer",
                "expiresIn": 7200,
                "refreshToken": "test_refresh_token",
            },
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_sites",
            return_value=[{"siteId": "site123", "name": "Test Site"}],
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_clients",
            return_value=[],
        ),
        patch("custom_components.omada_open_api.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_REGION: "us"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_OMADA_ID: "test_omada_id",
                CONF_CLIENT_ID: "test_client_id",
                CONF_CLIENT_SECRET: "test_client_secret",
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SELECTED_SITES: ["site123"]}
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "Omada - Test Site"
        assert result["data"][CONF_ACCESS_TOKEN] == "test_access_token"
        assert result["data"][CONF_REFRESH_TOKEN] == "test_refresh_token"


async def test_complete_local_flow_with_token_storage(hass: HomeAssistant) -> None:
    """Test complete local controller flow with token storage in config entry."""
    with (
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_access_token",
            return_value={
                "accessToken": "test_access_token",
                "tokenType": "bearer",
                "expiresIn": 7200,
                "refreshToken": "test_refresh_token",
            },
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_sites",
            return_value=[{"siteId": "site456", "name": "Local Site"}],
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_clients",
            return_value=[],
        ),
        patch("custom_components.omada_open_api.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CONTROLLER_TYPE: "local"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_URL: "https://omada.local:8043"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_OMADA_ID: "test_omada_id",
                CONF_CLIENT_ID: "test_client_id",
                CONF_CLIENT_SECRET: "test_client_secret",
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SELECTED_SITES: ["site456"]}
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "Omada - Local Site"
        assert result["data"][CONF_ACCESS_TOKEN] == "test_access_token"
        assert result["data"][CONF_REFRESH_TOKEN] == "test_refresh_token"


async def test_site_selection_multiple_sites(hass: HomeAssistant) -> None:
    """Test selecting multiple sites creates entry with proper title."""
    with (
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_access_token",
            return_value={
                "accessToken": "test_access_token",
                "tokenType": "bearer",
                "expiresIn": 7200,
                "refreshToken": "test_refresh_token",
            },
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_sites",
            return_value=[
                {"siteId": "site1", "name": "Office"},
                {"siteId": "site2", "name": "Home"},
                {"siteId": "site3", "name": "Warehouse"},
            ],
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_clients",
            return_value=[],
        ),
        patch("custom_components.omada_open_api.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_REGION: "us"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_OMADA_ID: "test_omada_id",
                CONF_CLIENT_ID: "test_client_id",
                CONF_CLIENT_SECRET: "test_client_secret",
            },
        )
        # Select multiple sites
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SELECTED_SITES: ["site1", "site2", "site3"]}
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "Omada - Office (+2)"
        assert result["data"][CONF_SELECTED_SITES] == ["site1", "site2", "site3"]
        assert len(result["data"][CONF_SELECTED_SITES]) == 3


# ---------------------------------------------------------------------------
# Unique config entry deduplication
# ---------------------------------------------------------------------------


async def test_unique_config_entry_abort(hass: HomeAssistant) -> None:
    """Test that a duplicate omada_id aborts the flow."""
    # Create an existing entry with omada_id "existing_omada"
    existing = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_URL: "https://test.example.com",
            CONF_OMADA_ID: "existing_omada",
            CONF_CLIENT_ID: "cid",
            CONF_CLIENT_SECRET: "csecret",
            CONF_ACCESS_TOKEN: "token",
            CONF_REFRESH_TOKEN: "rtoken",
            CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
            CONF_SELECTED_SITES: ["site1"],
        },
        unique_id="existing_omada",
    )
    existing.add_to_hass(hass)

    # Start a new flow with the same omada_id
    with (
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_access_token",
            return_value=MOCK_TOKEN_DATA,
        ),
        patch("custom_components.omada_open_api.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_REGION: "us"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_OMADA_ID: "existing_omada",
                CONF_CLIENT_ID: "new_cid",
                CONF_CLIENT_SECRET: "new_csecret",
            },
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# ---------------------------------------------------------------------------
# Data / options separation
# ---------------------------------------------------------------------------


async def test_entry_stores_options_separately(hass: HomeAssistant) -> None:
    """Test that client and app selections are stored in entry.options."""
    with (
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_access_token",
            return_value=MOCK_TOKEN_DATA,
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_sites",
            return_value=MOCK_SITES,
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_clients",
            return_value=MOCK_CLIENTS,
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_applications",
            return_value=MOCK_APPLICATIONS,
        ),
        patch("custom_components.omada_open_api.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_REGION: "us"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_OMADA_ID: "omada_options_test",
                CONF_CLIENT_ID: "cid",
                CONF_CLIENT_SECRET: "csecret",
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SELECTED_SITES: ["site123"]}
        )
        # Select clients
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_SELECTED_CLIENTS: ["AA-BB-CC-DD-EE-01"]},
        )
        # Select applications
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_SELECTED_APPLICATIONS: ["100"]},
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    # Selections must be in options, not data
    assert CONF_SELECTED_CLIENTS not in result["data"]
    assert CONF_SELECTED_APPLICATIONS not in result["data"]
    assert result["options"][CONF_SELECTED_CLIENTS] == ["AA-BB-CC-DD-EE-01"]
    assert result["options"][CONF_SELECTED_APPLICATIONS] == ["100"]


# ---------------------------------------------------------------------------
# Client selection step
# ---------------------------------------------------------------------------


async def test_clients_step_with_available_clients(hass: HomeAssistant) -> None:
    """Test that client selection step shows available clients."""
    with (
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_access_token",
            return_value=MOCK_TOKEN_DATA,
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_sites",
            return_value=MOCK_SITES,
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_clients",
            return_value=MOCK_CLIENTS,
        ),
        patch("custom_components.omada_open_api.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_REGION: "us"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_OMADA_ID: "omada_clients",
                CONF_CLIENT_ID: "cid",
                CONF_CLIENT_SECRET: "csecret",
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SELECTED_SITES: ["site123"]}
        )

    # Should show client selection form
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "clients"


async def test_clients_step_no_clients_skips(hass: HomeAssistant) -> None:
    """Test that no available clients skips to entry creation."""
    with (
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_access_token",
            return_value=MOCK_TOKEN_DATA,
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_sites",
            return_value=MOCK_SITES,
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_clients",
            return_value=[],
        ),
        patch("custom_components.omada_open_api.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_REGION: "us"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_OMADA_ID: "omada_no_clients",
                CONF_CLIENT_ID: "cid",
                CONF_CLIENT_SECRET: "csecret",
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SELECTED_SITES: ["site123"]}
        )

    # No clients → entry created immediately
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_SELECTED_CLIENTS] == []


async def test_clients_step_fetch_error(hass: HomeAssistant) -> None:
    """Test client fetch error falls back to entry creation."""
    with (
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_access_token",
            return_value=MOCK_TOKEN_DATA,
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_sites",
            return_value=MOCK_SITES,
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_clients",
            side_effect=Exception("API error"),
        ),
        patch("custom_components.omada_open_api.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_REGION: "us"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_OMADA_ID: "omada_client_err",
                CONF_CLIENT_ID: "cid",
                CONF_CLIENT_SECRET: "csecret",
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SELECTED_SITES: ["site123"]}
        )

    # Fetch error → entry created with empty clients
    assert result["type"] == FlowResultType.CREATE_ENTRY


# ---------------------------------------------------------------------------
# Application selection step
# ---------------------------------------------------------------------------


async def test_applications_step_with_apps(hass: HomeAssistant) -> None:
    """Test application selection step shows available apps."""
    with (
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_access_token",
            return_value=MOCK_TOKEN_DATA,
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_sites",
            return_value=MOCK_SITES,
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_clients",
            return_value=MOCK_CLIENTS,
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_applications",
            return_value=MOCK_APPLICATIONS,
        ),
        patch("custom_components.omada_open_api.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_REGION: "us"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_OMADA_ID: "omada_apps",
                CONF_CLIENT_ID: "cid",
                CONF_CLIENT_SECRET: "csecret",
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SELECTED_SITES: ["site123"]}
        )
        # Select clients
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_SELECTED_CLIENTS: ["AA-BB-CC-DD-EE-01"]},
        )

    # Should show application selection form
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "applications"


async def test_applications_step_no_apps_skips(hass: HomeAssistant) -> None:
    """Test that no available apps skips to entry creation."""
    with (
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_access_token",
            return_value=MOCK_TOKEN_DATA,
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_sites",
            return_value=MOCK_SITES,
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_clients",
            return_value=MOCK_CLIENTS,
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_applications",
            return_value=[],
        ),
        patch("custom_components.omada_open_api.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_REGION: "us"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_OMADA_ID: "omada_no_apps",
                CONF_CLIENT_ID: "cid",
                CONF_CLIENT_SECRET: "csecret",
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SELECTED_SITES: ["site123"]}
        )
        # Select clients
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_SELECTED_CLIENTS: ["AA-BB-CC-DD-EE-01"]},
        )

    # No apps → entry created immediately
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_SELECTED_APPLICATIONS] == []


# ---------------------------------------------------------------------------
# Credentials step - error recovery
# ---------------------------------------------------------------------------


async def test_credentials_aiohttp_error(hass: HomeAssistant) -> None:
    """Test that aiohttp.ClientError shows cannot_connect."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REGION: "us"}
    )

    with patch(
        "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_access_token",
        side_effect=aiohttp.ClientError("connection refused"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_OMADA_ID: "test",
                CONF_CLIENT_ID: "cid",
                CONF_CLIENT_SECRET: "csecret",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


async def test_credentials_no_sites_error(hass: HomeAssistant) -> None:
    """Test that no sites found shows error."""
    with (
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_access_token",
            return_value=MOCK_TOKEN_DATA,
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_sites",
            return_value=[],
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_REGION: "us"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_OMADA_ID: "no_sites_omada",
                CONF_CLIENT_ID: "cid",
                CONF_CLIENT_SECRET: "csecret",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "no_sites"


async def test_local_invalid_url(hass: HomeAssistant) -> None:
    """Test that invalid local URL shows error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CONTROLLER_TYPE: "local"}
    )
    # URL without http/https prefix
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_URL: "omada.local:8043"}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "local"
    assert result["errors"][CONF_API_URL] == "invalid_url"


# ---------------------------------------------------------------------------
# Reauth flow
# ---------------------------------------------------------------------------


async def test_reauth_flow_success(hass: HomeAssistant) -> None:
    """Test successful reauthentication flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_URL: "https://test.example.com",
            CONF_OMADA_ID: "reauth_omada",
            CONF_CLIENT_ID: "old_cid",
            CONF_CLIENT_SECRET: "old_csecret",
            CONF_ACCESS_TOKEN: "expired_token",
            CONF_REFRESH_TOKEN: "expired_rtoken",
            CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
            CONF_SELECTED_SITES: ["site1"],
        },
        unique_id="reauth_omada",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    with (
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_access_token",
            return_value=MOCK_TOKEN_DATA,
        ),
        patch("custom_components.omada_open_api.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_OMADA_ID: "reauth_omada",
                CONF_CLIENT_ID: "new_cid",
                CONF_CLIENT_SECRET: "new_csecret",
            },
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_CLIENT_ID] == "new_cid"
    assert entry.data[CONF_ACCESS_TOKEN] == "test_access_token"


async def test_reauth_flow_invalid_auth(hass: HomeAssistant) -> None:
    """Test reauthentication with invalid credentials shows error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_URL: "https://test.example.com",
            CONF_OMADA_ID: "reauth_fail",
            CONF_CLIENT_ID: "cid",
            CONF_CLIENT_SECRET: "csecret",
            CONF_ACCESS_TOKEN: "token",
            CONF_REFRESH_TOKEN: "rtoken",
            CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
            CONF_SELECTED_SITES: ["site1"],
        },
        unique_id="reauth_fail",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await entry.start_reauth_flow(hass)

    with patch(
        "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_access_token",
        side_effect=InvalidAuthError("bad creds"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_OMADA_ID: "reauth_fail",
                CONF_CLIENT_ID: "bad_cid",
                CONF_CLIENT_SECRET: "bad_csecret",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"


async def test_reauth_flow_connection_error(hass: HomeAssistant) -> None:
    """Test reauthentication with connection error shows error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_URL: "https://test.example.com",
            CONF_OMADA_ID: "reauth_conn",
            CONF_CLIENT_ID: "cid",
            CONF_CLIENT_SECRET: "csecret",
            CONF_ACCESS_TOKEN: "token",
            CONF_REFRESH_TOKEN: "rtoken",
            CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
            CONF_SELECTED_SITES: ["site1"],
        },
        unique_id="reauth_conn",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await entry.start_reauth_flow(hass)

    with patch(
        "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_access_token",
        side_effect=aiohttp.ClientError("timeout"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_OMADA_ID: "reauth_conn",
                CONF_CLIENT_ID: "cid",
                CONF_CLIENT_SECRET: "csecret",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


async def test_reauth_flow_unknown_error(hass: HomeAssistant) -> None:
    """Test reauthentication with unknown error shows error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_URL: "https://test.example.com",
            CONF_OMADA_ID: "reauth_unk",
            CONF_CLIENT_ID: "cid",
            CONF_CLIENT_SECRET: "csecret",
            CONF_ACCESS_TOKEN: "token",
            CONF_REFRESH_TOKEN: "rtoken",
            CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
            CONF_SELECTED_SITES: ["site1"],
        },
        unique_id="reauth_unk",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await entry.start_reauth_flow(hass)

    with patch(
        "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_access_token",
        side_effect=RuntimeError("something unexpected"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_OMADA_ID: "reauth_unk",
                CONF_CLIENT_ID: "cid",
                CONF_CLIENT_SECRET: "csecret",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "unknown"


# ---------------------------------------------------------------------------
# Options flow: client selection
# ---------------------------------------------------------------------------


async def test_options_client_selection(hass: HomeAssistant) -> None:
    """Test options flow client selection step."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_URL: "https://test.example.com",
            CONF_OMADA_ID: "opt_client",
            CONF_CLIENT_ID: "cid",
            CONF_CLIENT_SECRET: "csecret",
            CONF_ACCESS_TOKEN: "token",
            CONF_REFRESH_TOKEN: "rtoken",
            CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
            CONF_SELECTED_SITES: ["site1"],
        },
        options={CONF_SELECTED_CLIENTS: []},
    )
    entry.add_to_hass(hass)

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.MENU

    with patch(
        "custom_components.omada_open_api.config_flow.OmadaOptionsFlowHandler._get_clients",
        return_value=MOCK_CLIENTS,
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {"next_step_id": "client_selection"},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "client_selection"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SELECTED_CLIENTS: ["AA-BB-CC-DD-EE-01"]},
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SELECTED_CLIENTS] == ["AA-BB-CC-DD-EE-01"]


async def test_options_client_selection_no_clients(hass: HomeAssistant) -> None:
    """Test options flow client selection with no clients available."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_URL: "https://test.example.com",
            CONF_OMADA_ID: "opt_no_cl",
            CONF_CLIENT_ID: "cid",
            CONF_CLIENT_SECRET: "csecret",
            CONF_ACCESS_TOKEN: "token",
            CONF_REFRESH_TOKEN: "rtoken",
            CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
            CONF_SELECTED_SITES: ["site1"],
        },
        options={CONF_SELECTED_CLIENTS: []},
    )
    entry.add_to_hass(hass)

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)

    with patch(
        "custom_components.omada_open_api.config_flow.OmadaOptionsFlowHandler._get_clients",
        return_value=[],
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {"next_step_id": "client_selection"},
        )

    # No clients → entry created immediately
    assert result["type"] == FlowResultType.CREATE_ENTRY


# ---------------------------------------------------------------------------
# Options flow: application selection
# ---------------------------------------------------------------------------


async def test_options_application_selection(hass: HomeAssistant) -> None:
    """Test options flow application selection step."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_URL: "https://test.example.com",
            CONF_OMADA_ID: "opt_apps",
            CONF_CLIENT_ID: "cid",
            CONF_CLIENT_SECRET: "csecret",
            CONF_ACCESS_TOKEN: "token",
            CONF_REFRESH_TOKEN: "rtoken",
            CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
            CONF_SELECTED_SITES: ["site1"],
        },
        options={CONF_SELECTED_APPLICATIONS: []},
    )
    entry.add_to_hass(hass)

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)

    with patch(
        "custom_components.omada_open_api.config_flow.OmadaOptionsFlowHandler._get_applications",
        return_value=MOCK_APPLICATIONS,
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {"next_step_id": "application_selection"},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "application_selection"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SELECTED_APPLICATIONS: ["100"]},
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SELECTED_APPLICATIONS] == ["100"]


async def test_options_application_selection_no_apps(hass: HomeAssistant) -> None:
    """Test options flow application selection with no apps available."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_URL: "https://test.example.com",
            CONF_OMADA_ID: "opt_no_app",
            CONF_CLIENT_ID: "cid",
            CONF_CLIENT_SECRET: "csecret",
            CONF_ACCESS_TOKEN: "token",
            CONF_REFRESH_TOKEN: "rtoken",
            CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
            CONF_SELECTED_SITES: ["site1"],
        },
        options={CONF_SELECTED_APPLICATIONS: []},
    )
    entry.add_to_hass(hass)

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)

    with patch(
        "custom_components.omada_open_api.config_flow.OmadaOptionsFlowHandler._get_applications",
        return_value=[],
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {"next_step_id": "application_selection"},
        )

    # No apps → entry created immediately (options preserved)
    assert result["type"] == FlowResultType.CREATE_ENTRY


# ---------------------------------------------------------------------------
# Credentials step - InvalidAuthError specifically
# ---------------------------------------------------------------------------


async def test_credentials_invalid_auth_error(hass: HomeAssistant) -> None:
    """Test that InvalidAuthError from _get_access_token shows invalid_auth."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REGION: "us"}
    )

    with patch(
        "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_access_token",
        side_effect=InvalidAuthError("invalid client id"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_OMADA_ID: "test",
                CONF_CLIENT_ID: "bad_cid",
                CONF_CLIENT_SECRET: "bad_csecret",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "credentials"
    assert result["errors"]["base"] == "invalid_auth"


# ---------------------------------------------------------------------------
# Options flow - client/application fetch errors
# ---------------------------------------------------------------------------


async def test_options_client_selection_fetch_error(hass: HomeAssistant) -> None:
    """Test options flow client selection with fetch error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_URL: "https://test.example.com",
            CONF_OMADA_ID: "opt_cl_err",
            CONF_CLIENT_ID: "cid",
            CONF_CLIENT_SECRET: "csecret",
            CONF_ACCESS_TOKEN: "token",
            CONF_REFRESH_TOKEN: "rtoken",
            CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
            CONF_SELECTED_SITES: ["site1"],
        },
        options={CONF_SELECTED_CLIENTS: []},
    )
    entry.add_to_hass(hass)

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)

    with patch(
        "custom_components.omada_open_api.config_flow.OmadaOptionsFlowHandler._get_clients",
        side_effect=Exception("API error"),
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {"next_step_id": "client_selection"},
        )

    # Error → form with cannot_connect
    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


async def test_options_app_selection_fetch_error(hass: HomeAssistant) -> None:
    """Test options flow application selection with fetch error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_URL: "https://test.example.com",
            CONF_OMADA_ID: "opt_app_err",
            CONF_CLIENT_ID: "cid",
            CONF_CLIENT_SECRET: "csecret",
            CONF_ACCESS_TOKEN: "token",
            CONF_REFRESH_TOKEN: "rtoken",
            CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
            CONF_SELECTED_SITES: ["site1"],
        },
        options={CONF_SELECTED_APPLICATIONS: []},
    )
    entry.add_to_hass(hass)

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)

    with patch(
        "custom_components.omada_open_api.config_flow.OmadaOptionsFlowHandler._get_applications",
        side_effect=Exception("API error"),
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {"next_step_id": "application_selection"},
        )

    # Error → form with cannot_connect
    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


# ---------------------------------------------------------------------------
# Application step - completing selection with user input
# ---------------------------------------------------------------------------


async def test_complete_flow_with_applications(hass: HomeAssistant) -> None:
    """Test full flow through applications step with selection submitted."""
    with (
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_access_token",
            return_value=MOCK_TOKEN_DATA,
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_sites",
            return_value=MOCK_SITES,
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_clients",
            return_value=MOCK_CLIENTS,
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_applications",
            return_value=MOCK_APPLICATIONS,
        ),
        patch("custom_components.omada_open_api.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_REGION: "us"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_OMADA_ID: "omada_full",
                CONF_CLIENT_ID: "cid",
                CONF_CLIENT_SECRET: "csecret",
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SELECTED_SITES: ["site123"]}
        )
        # Select clients
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_SELECTED_CLIENTS: ["AA-BB-CC-DD-EE-01"]},
        )
        # Applications form shown
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "applications"

        # Submit application selection
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_SELECTED_APPLICATIONS: ["100", "200"]},
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Omada - Test Site"
    assert result["options"][CONF_SELECTED_CLIENTS] == ["AA-BB-CC-DD-EE-01"]
    assert result["options"][CONF_SELECTED_APPLICATIONS] == ["100", "200"]


# ---------------------------------------------------------------------------
# Application step fetch error → entry created without apps
# ---------------------------------------------------------------------------


async def test_applications_fetch_error_creates_entry(hass: HomeAssistant) -> None:
    """Test that app fetch error creates entry without apps."""
    with (
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_access_token",
            return_value=MOCK_TOKEN_DATA,
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_sites",
            return_value=MOCK_SITES,
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_clients",
            return_value=MOCK_CLIENTS,
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_applications",
            side_effect=Exception("DPI not supported"),
        ),
        patch("custom_components.omada_open_api.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_REGION: "us"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_OMADA_ID: "omada_app_err",
                CONF_CLIENT_ID: "cid",
                CONF_CLIENT_SECRET: "csecret",
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SELECTED_SITES: ["site123"]}
        )
        # Select clients
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_SELECTED_CLIENTS: ["AA-BB-CC-DD-EE-01"]},
        )

    # App fetch failed → entry created with empty apps
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_SELECTED_APPLICATIONS] == []


# ---------------------------------------------------------------------------
# HTTP-level tests for helper methods (using aioclient_mock)
# ---------------------------------------------------------------------------

# Base API URLs used in tests
_CLOUD_URL = "https://use1-omada-northbound.tplinkcloud.com"
_TOKEN_URL = f"{_CLOUD_URL}/openapi/authorize/token"
_SITES_URL = f"{_CLOUD_URL}/openapi/v1/test_omada/sites"
_CLIENTS_URL = f"{_CLOUD_URL}/openapi/v2/test_omada/sites/site123/clients"
_APPS_URL = (
    f"{_CLOUD_URL}/openapi/v1/test_omada/sites/site123/applicationControl/applications"
)


def _register_token_endpoint(aioclient_mock, status=200, json_data=None):
    """Register a mock token endpoint."""
    if json_data is None:
        json_data = {
            "errorCode": 0,
            "msg": "Success",
            "result": {
                "accessToken": "mock_access",
                "tokenType": "bearer",
                "expiresIn": 7200,
                "refreshToken": "mock_refresh",
            },
        }
    aioclient_mock.post(_TOKEN_URL, status=status, json=json_data)


def _register_sites_endpoint(aioclient_mock, status=200, json_data=None):
    """Register a mock sites endpoint."""
    if json_data is None:
        json_data = {
            "errorCode": 0,
            "msg": "Success",
            "result": {
                "data": [{"siteId": "site123", "name": "Test Site"}],
            },
        }
    aioclient_mock.get(_SITES_URL, status=status, json=json_data)


def _register_clients_endpoint(aioclient_mock, status=200, json_data=None):
    """Register a mock clients endpoint."""
    if json_data is None:
        json_data = {
            "errorCode": 0,
            "msg": "Success",
            "result": {
                "data": [
                    {"mac": "AA-BB-CC-DD-EE-01", "name": "Client1", "ip": "10.0.0.1"},
                ],
            },
        }
    aioclient_mock.post(_CLIENTS_URL, status=status, json=json_data)


def _register_apps_endpoint(aioclient_mock, status=200, json_data=None):
    """Register a mock applications endpoint."""
    if json_data is None:
        json_data = {
            "errorCode": 0,
            "msg": "Success",
            "result": {
                "data": [
                    {
                        "applicationId": 100,
                        "application": "YouTube",
                        "family": "Streaming",
                    },
                ],
                "totalRows": 1,
            },
        }
    aioclient_mock.get(_APPS_URL, status=status, json=json_data)


async def test_full_flow_http_level(hass: HomeAssistant, aioclient_mock) -> None:
    """Test full flow exercising real helper methods via HTTP mocks."""
    _register_token_endpoint(aioclient_mock)
    _register_sites_endpoint(aioclient_mock)
    _register_clients_endpoint(aioclient_mock)
    _register_apps_endpoint(aioclient_mock)

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_REGION: "us"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_OMADA_ID: "test_omada",
                CONF_CLIENT_ID: "cid",
                CONF_CLIENT_SECRET: "csecret",
            },
        )
        # Sites step
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "sites"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SELECTED_SITES: ["site123"]}
        )
        # Clients step
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "clients"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_SELECTED_CLIENTS: ["AA-BB-CC-DD-EE-01"]},
        )
        # Applications step
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "applications"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_SELECTED_APPLICATIONS: ["100"]},
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ACCESS_TOKEN] == "mock_access"
    assert result["options"][CONF_SELECTED_CLIENTS] == ["AA-BB-CC-DD-EE-01"]
    assert result["options"][CONF_SELECTED_APPLICATIONS] == ["100"]


async def test_get_access_token_401(hass: HomeAssistant, aioclient_mock) -> None:
    """Test _get_access_token with 401 response raises InvalidAuthError."""
    _register_token_endpoint(aioclient_mock, status=401)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REGION: "us"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_OMADA_ID: "test_omada",
            CONF_CLIENT_ID: "bad_cid",
            CONF_CLIENT_SECRET: "bad_csecret",
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"


async def test_get_access_token_500(hass: HomeAssistant, aioclient_mock) -> None:
    """Test _get_access_token with 500 response raises error."""
    _register_token_endpoint(
        aioclient_mock, status=500, json_data={"error": "server error"}
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REGION: "us"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_OMADA_ID: "test_omada",
            CONF_CLIENT_ID: "cid",
            CONF_CLIENT_SECRET: "csecret",
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


async def test_get_access_token_api_error_code(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Test _get_access_token with API error code raises InvalidAuthError."""
    _register_token_endpoint(
        aioclient_mock,
        json_data={"errorCode": -44106, "msg": "Invalid client credentials"},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REGION: "us"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_OMADA_ID: "test_omada",
            CONF_CLIENT_ID: "cid",
            CONF_CLIENT_SECRET: "csecret",
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"


async def test_get_sites_no_sites(hass: HomeAssistant, aioclient_mock) -> None:
    """Test _get_sites returns empty list shows no_sites error."""
    _register_token_endpoint(aioclient_mock)
    _register_sites_endpoint(
        aioclient_mock,
        json_data={"errorCode": 0, "result": {"data": []}},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REGION: "us"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_OMADA_ID: "test_omada",
            CONF_CLIENT_ID: "cid",
            CONF_CLIENT_SECRET: "csecret",
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "no_sites"


async def test_get_applications_api_error_returns_empty(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Test _get_applications with API error code returns empty list."""
    _register_token_endpoint(aioclient_mock)
    _register_sites_endpoint(aioclient_mock)
    _register_clients_endpoint(aioclient_mock)
    # Applications endpoint returns API error (DPI not enabled)
    _register_apps_endpoint(
        aioclient_mock,
        json_data={"errorCode": -1, "msg": "DPI not enabled"},
    )

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_REGION: "us"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_OMADA_ID: "test_omada",
                CONF_CLIENT_ID: "cid",
                CONF_CLIENT_SECRET: "csecret",
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SELECTED_SITES: ["site123"]}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_SELECTED_CLIENTS: ["AA-BB-CC-DD-EE-01"]},
        )

    # DPI error → entry created with empty apps
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_SELECTED_APPLICATIONS] == []


async def test_options_flow_http_level(hass: HomeAssistant, aioclient_mock) -> None:
    """Test options flow client/app selection using HTTP mocks."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_URL: _CLOUD_URL,
            CONF_OMADA_ID: "test_omada",
            CONF_CLIENT_ID: "cid",
            CONF_CLIENT_SECRET: "csecret",
            CONF_ACCESS_TOKEN: "token",
            CONF_REFRESH_TOKEN: "rtoken",
            CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
            CONF_SELECTED_SITES: ["site123"],
        },
        options={CONF_SELECTED_CLIENTS: [], CONF_SELECTED_APPLICATIONS: []},
    )
    entry.add_to_hass(hass)

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Test client selection via HTTP mock
    _register_clients_endpoint(aioclient_mock)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "client_selection"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "client_selection"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SELECTED_CLIENTS: ["AA-BB-CC-DD-EE-01"]},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SELECTED_CLIENTS] == ["AA-BB-CC-DD-EE-01"]

    # Test application selection via HTTP mock
    _register_apps_endpoint(aioclient_mock)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "application_selection"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "application_selection"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SELECTED_APPLICATIONS: ["100"]},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SELECTED_APPLICATIONS] == ["100"]


# ---------------------------------------------------------------------------
# HTTP-level error path tests for helper methods
# ---------------------------------------------------------------------------


async def test_get_sites_http_error(hass: HomeAssistant, aioclient_mock) -> None:
    """Test _get_sites with non-200 response raises error."""
    _register_token_endpoint(aioclient_mock)
    _register_sites_endpoint(aioclient_mock, status=500)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REGION: "us"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_OMADA_ID: "test_omada",
            CONF_CLIENT_ID: "cid",
            CONF_CLIENT_SECRET: "csecret",
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


async def test_get_sites_api_error(hass: HomeAssistant, aioclient_mock) -> None:
    """Test _get_sites with API error code raises InvalidAuthError."""
    _register_token_endpoint(aioclient_mock)
    _register_sites_endpoint(
        aioclient_mock,
        json_data={"errorCode": -1, "msg": "Unauthorized"},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REGION: "us"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_OMADA_ID: "test_omada",
            CONF_CLIENT_ID: "cid",
            CONF_CLIENT_SECRET: "csecret",
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"


async def test_get_clients_http_error(hass: HomeAssistant, aioclient_mock) -> None:
    """Test _get_clients with non-200 response shows error on clients step."""
    _register_token_endpoint(aioclient_mock)
    _register_sites_endpoint(aioclient_mock)
    _register_clients_endpoint(aioclient_mock, status=500)

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_REGION: "us"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_OMADA_ID: "test_omada",
                CONF_CLIENT_ID: "cid",
                CONF_CLIENT_SECRET: "csecret",
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SELECTED_SITES: ["site123"]}
        )

    # Client fetch error → entry created
    assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_get_clients_api_error(hass: HomeAssistant, aioclient_mock) -> None:
    """Test _get_clients with API error code creates entry."""
    _register_token_endpoint(aioclient_mock)
    _register_sites_endpoint(aioclient_mock)
    _register_clients_endpoint(
        aioclient_mock,
        json_data={"errorCode": -1, "msg": "Error"},
    )

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_REGION: "us"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_OMADA_ID: "test_omada",
                CONF_CLIENT_ID: "cid",
                CONF_CLIENT_SECRET: "csecret",
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SELECTED_SITES: ["site123"]}
        )

    # API error in clients → entry created with empty clients
    assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_get_apps_http_500_error(hass: HomeAssistant, aioclient_mock) -> None:
    """Test _get_applications with non-200 response."""
    _register_token_endpoint(aioclient_mock)
    _register_sites_endpoint(aioclient_mock)
    _register_clients_endpoint(aioclient_mock)
    _register_apps_endpoint(aioclient_mock, status=500)

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_REGION: "us"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_OMADA_ID: "test_omada",
                CONF_CLIENT_ID: "cid",
                CONF_CLIENT_SECRET: "csecret",
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SELECTED_SITES: ["site123"]}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_SELECTED_CLIENTS: ["AA-BB-CC-DD-EE-01"]},
        )

    # App fetch 500 → entry created with empty apps
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_SELECTED_APPLICATIONS] == []


async def test_get_apps_pagination(hass: HomeAssistant, aioclient_mock) -> None:
    """Test _get_applications with multi-page pagination."""
    _register_token_endpoint(aioclient_mock)
    _register_sites_endpoint(aioclient_mock)
    _register_clients_endpoint(aioclient_mock)

    # First page - 1000 apps, total 1500
    page1_apps = [
        {"applicationId": i, "application": f"App{i}", "family": "Cat"}
        for i in range(1000)
    ]
    aioclient_mock.get(
        _APPS_URL,
        json={
            "errorCode": 0,
            "result": {"data": page1_apps, "totalRows": 1500},
        },
    )
    # Second page - remaining 500 apps
    page2_apps = [
        {"applicationId": 1000 + i, "application": f"App{1000 + i}", "family": "Cat"}
        for i in range(500)
    ]
    aioclient_mock.get(
        _APPS_URL,
        json={
            "errorCode": 0,
            "result": {"data": page2_apps, "totalRows": 1500},
        },
    )

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_REGION: "us"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_OMADA_ID: "test_omada",
                CONF_CLIENT_ID: "cid",
                CONF_CLIENT_SECRET: "csecret",
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_SELECTED_SITES: ["site123"]}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_SELECTED_CLIENTS: ["AA-BB-CC-DD-EE-01"]},
        )

    # Should show applications form with 1500 apps
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "applications"


async def test_options_clients_http_error(hass: HomeAssistant, aioclient_mock) -> None:
    """Test options flow _get_clients with non-200 response."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_URL: _CLOUD_URL,
            CONF_OMADA_ID: "test_omada",
            CONF_CLIENT_ID: "cid",
            CONF_CLIENT_SECRET: "csecret",
            CONF_ACCESS_TOKEN: "token",
            CONF_REFRESH_TOKEN: "rtoken",
            CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
            CONF_SELECTED_SITES: ["site123"],
        },
        options={CONF_SELECTED_CLIENTS: []},
    )
    entry.add_to_hass(hass)

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    _register_clients_endpoint(aioclient_mock, status=500)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "client_selection"},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


async def test_options_clients_api_error(hass: HomeAssistant, aioclient_mock) -> None:
    """Test options flow _get_clients with API error code."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_URL: _CLOUD_URL,
            CONF_OMADA_ID: "test_omada",
            CONF_CLIENT_ID: "cid",
            CONF_CLIENT_SECRET: "csecret",
            CONF_ACCESS_TOKEN: "token",
            CONF_REFRESH_TOKEN: "rtoken",
            CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
            CONF_SELECTED_SITES: ["site123"],
        },
        options={CONF_SELECTED_CLIENTS: []},
    )
    entry.add_to_hass(hass)

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    _register_clients_endpoint(
        aioclient_mock,
        json_data={"errorCode": -1, "msg": "Error"},
    )
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "client_selection"},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


async def test_options_apps_http_error(hass: HomeAssistant, aioclient_mock) -> None:
    """Test options flow _get_applications with non-200 response."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_URL: _CLOUD_URL,
            CONF_OMADA_ID: "test_omada",
            CONF_CLIENT_ID: "cid",
            CONF_CLIENT_SECRET: "csecret",
            CONF_ACCESS_TOKEN: "token",
            CONF_REFRESH_TOKEN: "rtoken",
            CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
            CONF_SELECTED_SITES: ["site123"],
        },
        options={CONF_SELECTED_APPLICATIONS: []},
    )
    entry.add_to_hass(hass)

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    _register_apps_endpoint(aioclient_mock, status=500)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "application_selection"},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


async def test_options_apps_api_error(hass: HomeAssistant, aioclient_mock) -> None:
    """Test options flow _get_applications with API error returns empty."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_URL: _CLOUD_URL,
            CONF_OMADA_ID: "test_omada",
            CONF_CLIENT_ID: "cid",
            CONF_CLIENT_SECRET: "csecret",
            CONF_ACCESS_TOKEN: "token",
            CONF_REFRESH_TOKEN: "rtoken",
            CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
            CONF_SELECTED_SITES: ["site123"],
        },
        options={CONF_SELECTED_APPLICATIONS: []},
    )
    entry.add_to_hass(hass)

    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    _register_apps_endpoint(
        aioclient_mock,
        json_data={"errorCode": -1, "msg": "DPI not supported"},
    )
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "application_selection"},
    )

    # API error → entry created with existing options
    assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_empty_site_selection_default_title(
    hass: HomeAssistant,
) -> None:
    """Test that selecting no sites produces 'Omada Controller' as the title."""
    with (
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_access_token",
            return_value=MOCK_TOKEN_DATA,
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_sites",
            return_value=MOCK_SITES,
        ),
        patch(
            "custom_components.omada_open_api.async_setup_entry",
            return_value=True,
        ),
    ):
        # Start config flow through user → cloud → credentials → sites
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CONTROLLER_TYPE: "cloud"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"region": "us"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_OMADA_ID: "test_omada_id",
                CONF_CLIENT_ID: "test_client_id",
                CONF_CLIENT_SECRET: "test_client_secret",
            },
        )

        # Submit sites step with empty selection
        assert result["step_id"] == "sites"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_SELECTED_SITES: []},
        )

        # No sites → no clients fetched → entry created with default title
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "Omada Controller"


async def test_options_apps_pagination(hass: HomeAssistant, aioclient_mock) -> None:
    """Test options flow apps fetch with pagination (multiple pages)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CONTROLLER_TYPE: "cloud",
            CONF_API_URL: "https://use1-omada-northbound.tplinkcloud.com",
            CONF_OMADA_ID: "test_omada_id",
            CONF_CLIENT_ID: "test_client_id",
            CONF_CLIENT_SECRET: "test_client_secret",
            CONF_ACCESS_TOKEN: "test_token",
            CONF_REFRESH_TOKEN: "test_refresh",
            CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
            CONF_SELECTED_SITES: ["site_1"],
        },
        options={
            CONF_SELECTED_CLIENTS: [],
            CONF_SELECTED_APPLICATIONS: [],
        },
    )
    entry.add_to_hass(hass)
    with patch("custom_components.omada_open_api.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Register two pages of application data for options flow
    options_apps_url = (
        "https://use1-omada-northbound.tplinkcloud.com/openapi/v1/test_omada_id"
        "/sites/site_1/applicationControl/applications"
    )
    # Page 1: returns full page (1000 apps), totalRows=1001 (more pages needed)
    page1_apps = [
        {"applicationId": i, "application": f"App_{i}", "family": "Video"}
        for i in range(1000)
    ]
    aioclient_mock.get(
        options_apps_url,
        json={
            "errorCode": 0,
            "msg": "Success",
            "result": {
                "totalRows": 1001,
                "data": page1_apps,
            },
        },
    )
    # Page 2: returns 1 app, completes pagination
    aioclient_mock.get(
        options_apps_url,
        json={
            "errorCode": 0,
            "msg": "Success",
            "result": {
                "totalRows": 1001,
                "data": [
                    {
                        "applicationId": 9999,
                        "application": "LastApp",
                        "family": "Other",
                    },
                ],
            },
        },
    )

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "application_selection"},
    )

    # Should show form with all 3 apps from 2 pages
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "application_selection"


# ---------------------------------------------------------------------------
# Reconfigure flow tests
# ---------------------------------------------------------------------------


async def test_reconfigure_shows_form(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Test that reconfigure flow shows form with current values."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_URL: "https://old.example.com",
            CONF_OMADA_ID: "old_omada_id",
            CONF_CLIENT_ID: "old_client_id",
            CONF_CLIENT_SECRET: "old_secret",
            CONF_ACCESS_TOKEN: "old_token",
            CONF_REFRESH_TOKEN: "old_refresh",
            CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
            CONF_SELECTED_SITES: ["site1"],
            CONF_CONTROLLER_TYPE: CONTROLLER_TYPE_CLOUD,
            CONF_REGION: "us",
        },
        entry_id="test_reconfig",
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"


async def test_reconfigure_full_flow_cloud(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Test successful reconfigure with cloud controller."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_URL: "https://old.example.com",
            CONF_OMADA_ID: "old_omada_id",
            CONF_CLIENT_ID: "old_client_id",
            CONF_CLIENT_SECRET: "old_secret",
            CONF_ACCESS_TOKEN: "old_token",
            CONF_REFRESH_TOKEN: "old_refresh",
            CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
            CONF_SELECTED_SITES: ["site1"],
            CONF_CONTROLLER_TYPE: CONTROLLER_TYPE_CLOUD,
            CONF_REGION: "us",
        },
        entry_id="test_reconfig",
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_access_token",
            return_value=MOCK_TOKEN_DATA,
        ),
        patch(
            "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_sites",
            return_value=MOCK_SITES,
        ),
    ):
        result = await entry.start_reconfigure_flow(hass)
        assert result["step_id"] == "reconfigure"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_CONTROLLER_TYPE: CONTROLLER_TYPE_CLOUD,
                CONF_REGION: "eu",
                CONF_OMADA_ID: "new_omada_id",
                CONF_CLIENT_ID: "new_client_id",
                CONF_CLIENT_SECRET: "new_secret",
            },
        )

        assert result["step_id"] == "reconfigure_sites"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_SELECTED_SITES: ["site123"]},
        )

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "reconfigure_successful"
        assert entry.data[CONF_OMADA_ID] == "new_omada_id"
        assert entry.data[CONF_CLIENT_ID] == "new_client_id"
        assert entry.data[CONF_SELECTED_SITES] == ["site123"]


async def test_reconfigure_invalid_auth(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Test reconfigure handles invalid auth error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_URL: "https://old.example.com",
            CONF_OMADA_ID: "old_omada_id",
            CONF_CLIENT_ID: "old_client_id",
            CONF_CLIENT_SECRET: "old_secret",
            CONF_ACCESS_TOKEN: "old_token",
            CONF_REFRESH_TOKEN: "old_refresh",
            CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
            CONF_SELECTED_SITES: ["site1"],
            CONF_CONTROLLER_TYPE: CONTROLLER_TYPE_CLOUD,
            CONF_REGION: "us",
        },
        entry_id="test_reconfig",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.omada_open_api.config_flow.OmadaConfigFlow._get_access_token",
        side_effect=InvalidAuthError("Bad creds"),
    ):
        result = await entry.start_reconfigure_flow(hass)

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_CONTROLLER_TYPE: CONTROLLER_TYPE_CLOUD,
                CONF_REGION: "us",
                CONF_OMADA_ID: "bad_id",
                CONF_CLIENT_ID: "bad_client",
                CONF_CLIENT_SECRET: "bad_secret",
            },
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "reconfigure"
        assert result["errors"]["base"] == "invalid_auth"


async def test_reconfigure_local_invalid_url(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Test reconfigure rejects invalid local URL."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_URL: "https://local.example.com",
            CONF_OMADA_ID: "omada_id",
            CONF_CLIENT_ID: "client_id",
            CONF_CLIENT_SECRET: "secret",
            CONF_ACCESS_TOKEN: "token",
            CONF_REFRESH_TOKEN: "refresh",
            CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
            CONF_SELECTED_SITES: ["site1"],
            CONF_CONTROLLER_TYPE: CONTROLLER_TYPE_LOCAL,
        },
        entry_id="test_reconfig",
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_CONTROLLER_TYPE: CONTROLLER_TYPE_LOCAL,
            CONF_API_URL: "not-a-url",
            CONF_OMADA_ID: "omada_id",
            CONF_CLIENT_ID: "client_id",
            CONF_CLIENT_SECRET: "secret",
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"]["base"] == "invalid_url"
