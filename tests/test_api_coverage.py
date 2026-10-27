"""Tests for OmadaApiClient paths not covered elsewhere."""

from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.omada_open_api.api import OmadaApiClient, OmadaApiError

from .conftest import TEST_API_URL, TEST_OMADA_ID

SITE_ID = "site_001"
AP_MAC = "AA-BB-CC-DD-EE-01"


def _client(*, auth: MagicMock | None = None) -> OmadaApiClient:
    """Create a client with dummy credentials."""
    return OmadaApiClient(
        session=MagicMock(),
        token_update_callback=AsyncMock(),
        api_url=f"{TEST_API_URL}/",
        omada_id=TEST_OMADA_ID,
        client_id="client_id",
        client_secret="client_secret",
        access_token="access_token",
        refresh_token="refresh_token",
        token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
        auth=auth,
    )


def test_injected_auth_strategy_is_used() -> None:
    """An injected auth strategy replaces the client-credentials default."""
    auth = MagicMock()
    client = _client(auth=auth)

    assert client.auth is auth
    assert client.api_url == TEST_API_URL


async def test_update_ap_ssid_override_patches_full_list() -> None:
    """Only the target SSID changes; other overrides keep their state."""
    client = _client()
    current = {
        "ssidOverrides": [
            {"ssidEntryId": 1, "overrideSsidEnable": True, "ssidEnable": True},
            {"ssidEntryId": 2, "overrideVlanEnable": True, "ssidEnable": False},
            {"ssidEntryId": 3},
        ]
    }
    with (
        patch.object(client, "get_ap_ssid_overrides", AsyncMock(return_value=current)),
        patch.object(client, "_authenticated_request", AsyncMock()) as request,
    ):
        await client.update_ap_ssid_override(SITE_ID, AP_MAC, 1, "Home", False)

    method, url = request.call_args.args
    assert method == "patch"
    assert url.endswith(f"/sites/{SITE_ID}/aps/{AP_MAC}/override")
    assert request.call_args.kwargs["json_data"] == {
        "ssidOverrides": [
            {
                "ssidEntryId": 1,
                "overrideSsidEnable": True,
                "overrideVlanEnable": False,
                "ssidEnable": False,
            },
            {
                "ssidEntryId": 2,
                "overrideSsidEnable": False,
                "overrideVlanEnable": True,
                "ssidEnable": False,
            },
            {
                "ssidEntryId": 3,
                "overrideSsidEnable": False,
                "overrideVlanEnable": False,
            },
        ]
    }


async def test_get_ap_ssid_overrides_returns_result() -> None:
    """The override payload is unwrapped from the API result."""
    client = _client()
    result = {"ssidOverrides": []}
    with patch.object(
        client, "_authenticated_request", AsyncMock(return_value={"result": result})
    ):
        assert await client.get_ap_ssid_overrides(SITE_ID, AP_MAC) == result


async def test_check_write_access_unexpected_api_error_assumes_access() -> None:
    """Errors other than permission denials do not hide write entities."""
    client = _client()
    with patch.object(
        client,
        "get_led_setting",
        AsyncMock(side_effect=OmadaApiError("boom", error_code=-1)),
    ):
        assert await client.check_write_access(SITE_ID) is True


async def test_check_write_access_unexpected_exception_assumes_access() -> None:
    """Unexpected exceptions during the probe assume write access."""
    client = _client()
    with patch.object(
        client, "get_led_setting", AsyncMock(side_effect=RuntimeError("boom"))
    ):
        assert await client.check_write_access(SITE_ID) is True
