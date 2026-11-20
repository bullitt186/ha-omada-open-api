"""Tests for Fusion Gateway config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.omada_open_api.const import (
    AUTH_MODE_WEB_SESSION,
    CONF_API_URL,
    CONF_AUTH_MODE,
    CONF_CONTROLLER_TYPE,
    CONF_OMADA_ID,
    CONF_PASSWORD,
    CONF_SELECTED_SITES,
    CONF_USERNAME,
    CONTROLLER_TYPE_FUSION,
    DOMAIN,
)


@pytest.fixture
def mock_fusion_responses():
    """Create mock responses for Fusion flow."""
    # /api/info response
    info_response = AsyncMock()
    info_response.status = 200
    info_response.json = AsyncMock(
        return_value={
            "errorCode": 0,
            "result": {"omadacId": "fusion_cid_123"},
        }
    )

    # Login response
    login_response = AsyncMock()
    login_response.status = 200
    login_response.json = AsyncMock(
        return_value={
            "errorCode": 0,
            "result": {"token": "csrf_token_abc"},
        }
    )

    # Sites response
    sites_response = AsyncMock()
    sites_response.status = 200
    sites_response.json = AsyncMock(
        return_value={
            "errorCode": 0,
            "result": {
                "data": [
                    {"siteId": "fusion_site_1", "name": "FUSION 2.5G_E9F148"},
                ],
            },
        }
    )

    return {
        "info": info_response,
        "login": login_response,
        "sites": sites_response,
    }


async def test_user_step_shows_fusion_option(hass: HomeAssistant) -> None:
    """Test that Fusion Gateway appears in controller type selection."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    # Verify fusion is in the schema options
    schema = result["data_schema"]
    schema_dict = dict(schema.schema)
    controller_type_key = next(iter(schema_dict))
    selector = schema_dict[controller_type_key]
    assert CONTROLLER_TYPE_FUSION in selector.config["options"]


async def test_fusion_step_renders_form(hass: HomeAssistant) -> None:
    """Test that selecting Fusion shows URL + username + password form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONTROLLER_TYPE: CONTROLLER_TYPE_FUSION},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "fusion"


async def test_fusion_flow_invalid_url(hass: HomeAssistant) -> None:
    """Test that invalid URL shows error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONTROLLER_TYPE: CONTROLLER_TYPE_FUSION},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_API_URL: "not-a-url",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "pass",
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_API_URL: "invalid_url"}


async def test_fusion_flow_invalid_credentials(
    hass: HomeAssistant,
) -> None:
    """Test that invalid credentials show error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONTROLLER_TYPE: CONTROLLER_TYPE_FUSION},
    )

    # Mock /api/info success but login failure
    info_response = AsyncMock()
    info_response.status = 200
    info_response.json = AsyncMock(
        return_value={
            "errorCode": 0,
            "result": {"omadacId": "fusion_cid_123"},
        }
    )

    login_response = AsyncMock()
    login_response.status = 200
    login_response.json = AsyncMock(
        return_value={
            "errorCode": -30109,
            "msg": "Invalid username or password",
        }
    )

    with (
        patch("aiohttp.ClientSession.get") as mock_get,
        patch("aiohttp.ClientSession.post") as mock_post,
    ):
        mock_get.return_value.__aenter__.return_value = info_response
        mock_post.return_value.__aenter__.return_value = login_response

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_API_URL: "https://192.168.1.1",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "wrong",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_fusion_flow_happy_path_single_site(
    hass: HomeAssistant, mock_fusion_responses
) -> None:
    """Test full Fusion flow with single site auto-select."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONTROLLER_TYPE: CONTROLLER_TYPE_FUSION},
    )

    # Mock responses for: GET /api/info, POST login, POST login (for sites), GET sites
    with (
        patch("aiohttp.ClientSession.get") as mock_get,
        patch("aiohttp.ClientSession.post") as mock_post,
        patch(
            "custom_components.omada_open_api.async_setup_entry",
            return_value=True,
        ),
    ):
        # GET calls: /api/info, then sites endpoint
        mock_get.return_value.__aenter__.side_effect = [
            mock_fusion_responses["info"],
            mock_fusion_responses["sites"],
        ]
        # POST calls: login (validation), login (for sites fetch)
        mock_post.return_value.__aenter__.side_effect = [
            mock_fusion_responses["login"],
            mock_fusion_responses["login"],
        ]

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_API_URL: "https://192.168.1.1",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "secret",
            },
        )

    # Single site should be auto-selected; flow proceeds past fusion step
    # (reaches ssid_filter or creates entry if client fetch fails gracefully)
    assert result["type"] in (FlowResultType.FORM, FlowResultType.CREATE_ENTRY)
    if result["type"] == FlowResultType.FORM:
        assert result["step_id"] == "ssid_filter"


async def test_fusion_entry_data_shape(
    hass: HomeAssistant, mock_fusion_responses
) -> None:
    """Test that a created Fusion entry has the correct data shape."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONTROLLER_TYPE: CONTROLLER_TYPE_FUSION},
    )

    # Empty clients response for all subsequent POST calls
    empty_clients_response = AsyncMock()
    empty_clients_response.status = 200
    empty_clients_response.json = AsyncMock(
        return_value={
            "errorCode": 0,
            "result": {"data": [], "totalRows": 0, "currentPage": 1},
        }
    )

    with (
        patch("aiohttp.ClientSession.get") as mock_get,
        patch("aiohttp.ClientSession.post") as mock_post,
        patch(
            "custom_components.omada_open_api.async_setup_entry",
            return_value=True,
        ),
    ):
        mock_get.return_value.__aenter__.side_effect = [
            mock_fusion_responses["info"],
            mock_fusion_responses["sites"],
        ]
        # Login + login for sites + any subsequent client fetches
        mock_post.return_value.__aenter__.side_effect = [
            mock_fusion_responses["login"],
            mock_fusion_responses["login"],
            empty_clients_response,
            empty_clients_response,
            empty_clients_response,
        ]

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_API_URL: "https://192.168.1.1",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "secret",
            },
        )

    # Flow creates entry when clients can't be fetched or are empty
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CONTROLLER_TYPE] == CONTROLLER_TYPE_FUSION
    assert result["data"][CONF_AUTH_MODE] == AUTH_MODE_WEB_SESSION
    assert result["data"][CONF_API_URL] == "https://192.168.1.1"
    assert result["data"][CONF_OMADA_ID] == "fusion_cid_123"
    assert result["data"][CONF_USERNAME] == "admin"
    assert result["data"][CONF_PASSWORD] == "secret"
    assert result["data"][CONF_SELECTED_SITES] == ["fusion_site_1"]
    # Should NOT have OpenAPI-specific fields
    assert "client_id" not in result["data"]
    assert "client_secret" not in result["data"]
    assert "access_token" not in result["data"]


def _response(status: int, payload: dict | None) -> AsyncMock:
    """Build a mocked aiohttp response."""
    response = AsyncMock()
    response.status = status
    response.text = AsyncMock(return_value="error")
    response.json = AsyncMock(return_value=payload)
    return response


async def _submit_fusion_form(
    hass: HomeAssistant, get_responses: list, post_responses: list
) -> tuple[dict, MagicMock, MagicMock]:
    """Submit the Fusion step with the given GET and POST responses."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CONTROLLER_TYPE: CONTROLLER_TYPE_FUSION},
    )
    with (
        patch("aiohttp.ClientSession.get") as mock_get,
        patch("aiohttp.ClientSession.post") as mock_post,
        patch(
            "custom_components.omada_open_api.async_setup_entry",
            return_value=True,
        ),
    ):
        mock_get.return_value.__aenter__.side_effect = get_responses
        mock_post.return_value.__aenter__.side_effect = post_responses
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_API_URL: "https://192.168.1.1/",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "secret",
            },
        )
    return result, mock_get, mock_post


async def test_fusion_flow_sends_requests_through_one_session(
    hass: HomeAssistant, mock_fusion_responses
) -> None:
    """Info, login and sites requests use the documented URLs and CSRF header."""
    result, mock_get, mock_post = await _submit_fusion_form(
        hass,
        [mock_fusion_responses["info"], mock_fusion_responses["sites"]],
        [
            mock_fusion_responses["login"],
            _response(200, {"errorCode": 0, "result": {"data": [], "totalRows": 0}}),
        ],
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    info_call, sites_call = mock_get.call_args_list
    assert info_call.args == ("https://192.168.1.1/api/info",)
    assert sites_call.args == ("https://192.168.1.1/openapi/v1/fusion_cid_123/sites",)
    assert sites_call.kwargs["params"] == {"page": 1, "pageSize": 100}
    assert sites_call.kwargs["headers"]["Csrf-Token"] == "csrf_token_abc"
    assert sites_call.kwargs["headers"]["Omada-Request-Source"] == "web-local"
    login_call = mock_post.call_args_list[0]
    assert login_call.args == ("https://192.168.1.1/fusion_cid_123/api/v2/login",)
    assert login_call.kwargs["json"] == {"username": "admin", "password": "secret"}


@pytest.mark.parametrize(
    ("info", "expected_error"),
    [
        ((500, {}), "cannot_connect"),
        ((200, {"errorCode": -1, "msg": "denied"}), "invalid_auth"),
        ((200, {"errorCode": 0, "result": {}}), "invalid_auth"),
    ],
)
async def test_fusion_flow_reports_controller_info_failures(
    hass: HomeAssistant, info: tuple[int, dict], expected_error: str
) -> None:
    """A failing or ID-less /api/info answer is reported on the form."""
    result, _, mock_post = await _submit_fusion_form(hass, [_response(*info)], [])

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": expected_error}
    mock_post.assert_not_called()


@pytest.mark.parametrize(
    ("sites", "expected_error"),
    [
        ((500, {}), "cannot_connect"),
        ((200, {"errorCode": -1, "msg": "denied"}), "invalid_auth"),
        ((200, {"errorCode": 0, "result": {"data": [], "totalRows": 0}}), "no_sites"),
    ],
)
async def test_fusion_flow_reports_site_list_failures(
    hass: HomeAssistant,
    mock_fusion_responses,
    sites: tuple[int, dict],
    expected_error: str,
) -> None:
    """Site list errors are reported on the form instead of as "no sites"."""
    result, _, _ = await _submit_fusion_form(
        hass,
        [mock_fusion_responses["info"], _response(*sites)],
        [mock_fusion_responses["login"]],
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": expected_error}


async def test_fusion_flow_reports_connection_refused(hass: HomeAssistant) -> None:
    """A refused connection to the gateway is classified as such."""
    refused = aiohttp.ClientConnectionError("Connection refused")
    result, _, _ = await _submit_fusion_form(hass, [refused], [])

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "connection_refused"}


async def test_fusion_flow_aborts_when_gateway_already_configured(
    hass: HomeAssistant, mock_fusion_responses
) -> None:
    """Adding the same Fusion gateway twice aborts as already_configured (GH #195)."""
    MockConfigEntry(domain=DOMAIN, unique_id="fusion_fusion_cid_123").add_to_hass(hass)

    result, _, _ = await _submit_fusion_form(
        hass, [mock_fusion_responses["info"]], [mock_fusion_responses["login"]]
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
