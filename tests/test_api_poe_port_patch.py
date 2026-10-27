"""Tests for the PoE port-object PATCH fallback in the API client."""

import datetime as dt
from typing import Any
from unittest.mock import AsyncMock, MagicMock

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

SWITCH_MAC = "AA-BB-CC-DD-EE-02"
SITE_ID = "site_001"

SWITCH_DETAIL: dict[str, Any] = {
    "errorCode": 0,
    "result": {
        "mac": SWITCH_MAC,
        "portList": [
            {
                "port": 1,
                "name": "uplink",
                "profileId": "profile_other",
                "profileOverrideEnable": False,
                "poeMode": 1,
            },
            {
                "port": 12,
                "name": "domofon",
                "profileId": "profile_all",
                "profileOverrideEnable": True,
                "poeMode": 1,
            },
        ],
    },
}

POE_INFO: dict[str, Any] = {
    "errorCode": 0,
    "result": {
        "totalRows": 1,
        "data": [
            {
                "port": 12,
                "switchMac": SWITCH_MAC,
                "portName": "domofon",
                "operation": "switching",
                "supportPoe": True,
                "switchSupportPoe": 1,
                "poe": 1,
                "linkSpeed": 2,
                "duplex": 2,
            }
        ],
    },
}


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


class _FakeResponse:
    """Minimal aiohttp response stand-in."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.status = 200
        self._payload = payload

    async def json(self, content_type: str | None = None) -> dict[str, Any]:
        """Return the canned payload."""
        return self._payload

    async def text(self) -> str:
        """Return an empty body."""
        return ""


class _FakeRequest:
    """Async context manager returning a canned response."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    async def __aenter__(self) -> _FakeResponse:
        """Enter the context and hand out the response."""
        return _FakeResponse(self._payload)

    async def __aexit__(self, *args: object) -> None:
        """Leave the context."""
        return


def _build_client(mock_config_entry, *, detail=SWITCH_DETAIL, poe_info=POE_INFO):
    """Build an API client whose GETs answer with canned controller payloads."""
    mock_session = MagicMock()

    def _get(url: str, **_kwargs: Any) -> _FakeRequest:
        payload = poe_info if "ports/poe-info" in url else detail
        return _FakeRequest(payload)

    mock_session.get = MagicMock(side_effect=_get)
    mock_session.patch = MagicMock(
        side_effect=lambda *_args, **_kwargs: _FakeRequest({"errorCode": 0})
    )

    return OmadaApiClient(
        session=mock_session,
        token_update_callback=AsyncMock(),
        api_url=mock_config_entry.data[CONF_API_URL],
        omada_id=mock_config_entry.data[CONF_OMADA_ID],
        client_id=mock_config_entry.data[CONF_CLIENT_ID],
        client_secret=mock_config_entry.data[CONF_CLIENT_SECRET],
        access_token=mock_config_entry.data[CONF_ACCESS_TOKEN],
        refresh_token=mock_config_entry.data[CONF_REFRESH_TOKEN],
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    ), mock_session


async def test_port_patch_disables_poe(hass: HomeAssistant, mock_config_entry) -> None:
    """Test the fallback patches the port object with poe 0."""
    api_client, mock_session = _build_client(mock_config_entry)

    await api_client.set_port_poe_via_port_patch(
        SITE_ID, SWITCH_MAC, 12, poe_enabled=False
    )

    call_url = mock_session.patch.call_args[0][0]
    assert call_url.endswith(f"/switches/{SWITCH_MAC}/ports/12")
    assert mock_session.patch.call_args[1]["json"] == {
        "profileId": "profile_all",
        "profileOverrideEnable": True,
        "operation": "switching",
        "poe": 0,
    }


async def test_port_patch_enables_poe(hass: HomeAssistant, mock_config_entry) -> None:
    """Test the fallback patches the port object with poe 1."""
    api_client, mock_session = _build_client(mock_config_entry)

    await api_client.set_port_poe_via_port_patch(
        SITE_ID, SWITCH_MAC, 12, poe_enabled=True
    )

    assert mock_session.patch.call_args[1]["json"]["poe"] == 1


async def test_port_patch_sends_no_other_port_settings(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test the body carries nothing that could overwrite other port settings.

    The controller merges this PATCH, so any field the body does not carry
    keeps its current value. Sending VLAN, speed or profile fields would
    risk overwriting them with reconstructed values.
    """
    api_client, mock_session = _build_client(mock_config_entry)

    await api_client.set_port_poe_via_port_patch(
        SITE_ID, SWITCH_MAC, 12, poe_enabled=False
    )

    body = mock_session.patch.call_args[1]["json"]
    assert set(body) == {"profileId", "profileOverrideEnable", "operation", "poe"}
    # Everything the body does carry was read back from the controller.
    assert body["profileId"] == SWITCH_DETAIL["result"]["portList"][1]["profileId"]
    assert body["operation"] == POE_INFO["result"]["data"][0]["operation"]


async def test_port_patch_unknown_port_raises(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test a port missing from the switch detail raises instead of guessing."""
    api_client, mock_session = _build_client(mock_config_entry)

    with pytest.raises(OmadaApiError, match="profile not readable"):
        await api_client.set_port_poe_via_port_patch(
            SITE_ID, SWITCH_MAC, 99, poe_enabled=False
        )

    mock_session.patch.assert_not_called()


async def test_port_patch_unknown_operation_raises(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Test an unreadable operation mode raises instead of assuming one."""
    empty_poe_info = {
        "errorCode": 0,
        "result": {"totalRows": 0, "data": []},
    }
    api_client, mock_session = _build_client(mock_config_entry, poe_info=empty_poe_info)

    with pytest.raises(OmadaApiError, match="operation mode not readable"):
        await api_client.set_port_poe_via_port_patch(
            SITE_ID, SWITCH_MAC, 12, poe_enabled=False
        )

    mock_session.patch.assert_not_called()
