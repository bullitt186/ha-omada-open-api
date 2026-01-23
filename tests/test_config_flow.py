"""Tests for Omada Open API config flow."""

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest

from custom_components.omada_open_api.const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_CONTROLLER_TYPE,
    CONF_OMADA_ID,
    CONF_REGION,
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
