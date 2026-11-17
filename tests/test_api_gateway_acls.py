"""Tests for gateway ACL API access (profile mode and custom mode)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.omada_open_api.api import OmadaApiClient, OmadaApiError

SITE = "https://controller.local/openapi/v1/controller-id/sites/site-id/acls"
MODE_URL = f"{SITE}/osg-config-mode"
PROFILE_URL = f"{SITE}/osg-acls"
CUSTOM_URL = f"{SITE}/osg-custom-acls"
BATCH_EDIT_URL = f"{SITE}/gateway-acls/batch-edit"

PROFILE_MODE = {"result": {"mode": 0}}
CUSTOM_MODE = {"result": {"mode": 1}}


def _client() -> OmadaApiClient:
    """Build a client without running __init__ (no HA session needed)."""
    client = OmadaApiClient.__new__(OmadaApiClient)
    client._api_url = "https://controller.local"
    client._omada_id = "controller-id"
    return client


@pytest.mark.asyncio
async def test_get_gateway_acl_config_mode_returns_mode() -> None:
    """The config mode is unwrapped from the result."""
    client = _client()
    client._authenticated_request = AsyncMock(return_value=CUSTOM_MODE)

    assert await client.get_gateway_acl_config_mode("site-id") == 1
    client._authenticated_request.assert_awaited_once_with("get", MODE_URL)


@pytest.mark.asyncio
async def test_get_gateway_acl_config_mode_defaults_to_profile_on_error() -> None:
    """Controllers without the mode endpoint are treated as profile mode."""
    client = _client()
    client._authenticated_request = AsyncMock(side_effect=OmadaApiError("nope"))

    assert await client.get_gateway_acl_config_mode("site-id") == 0


@pytest.mark.asyncio
async def test_get_gateway_acls_profile_mode_paginates_all_rows() -> None:
    """Profile mode reads osg-acls and follows totalRows until complete."""
    client = _client()
    first_page = [{"id": f"a{i}", "name": f"r{i}", "status": True} for i in range(100)]
    second_page = [{"id": "last", "name": "last", "status": False}]
    client._authenticated_request = AsyncMock(
        side_effect=[
            PROFILE_MODE,
            {"result": {"data": first_page, "totalRows": 101}},
            {"result": {"data": second_page, "totalRows": 101}},
        ]
    )

    rules = await client.get_gateway_acls("site-id")

    assert len(rules) == 101
    assert rules[-1]["id"] == "last"
    calls = client._authenticated_request.await_args_list
    assert calls[1].args == ("get", PROFILE_URL)
    assert calls[1].kwargs["params"] == {"page": 1, "pageSize": 100}
    assert calls[2].kwargs["params"] == {"page": 2, "pageSize": 100}


@pytest.mark.asyncio
async def test_get_gateway_acls_custom_mode_uses_description_as_name() -> None:
    """Custom mode reads osg-custom-acls and exposes the description as name."""
    client = _client()
    client._authenticated_request = AsyncMock(
        side_effect=[
            CUSTOM_MODE,
            {
                "result": {
                    "data": [{"id": "c1", "description": "Allow IoT", "status": True}],
                    "totalRows": 1,
                }
            },
        ]
    )

    rules = await client.get_gateway_acls("site-id")

    assert rules == [
        {"id": "c1", "description": "Allow IoT", "name": "Allow IoT", "status": True}
    ]
    assert client._authenticated_request.await_args_list[1].args == ("get", CUSTOM_URL)


@pytest.mark.asyncio
async def test_set_status_profile_mode_writes_back_full_rule() -> None:
    """Profile mode PUTs the complete rule with only 'status' changed."""
    client = _client()
    rule = {"id": "acl-1", "name": "Block IoT", "status": True, "policy": 0}
    client._authenticated_request = AsyncMock(
        side_effect=[
            PROFILE_MODE,
            {"result": {"data": [rule], "totalRows": 1}},
            {"errorCode": 0},
        ]
    )

    await client.set_gateway_acl_status("site-id", "acl-1", enabled=False)

    put_call = client._authenticated_request.await_args_list[2]
    assert put_call.args == ("put", f"{PROFILE_URL}/acl-1")
    assert put_call.kwargs["json_data"] == {
        "id": "acl-1",
        "name": "Block IoT",
        "status": False,
        "policy": 0,
    }
    # The list rule must not be mutated.
    assert rule["status"] is True


@pytest.mark.asyncio
async def test_set_status_custom_mode_uses_batch_edit() -> None:
    """Custom mode toggles via batch-edit and keeps the current log status."""
    client = _client()
    client._authenticated_request = AsyncMock(
        side_effect=[
            CUSTOM_MODE,
            {
                "result": {
                    "data": [
                        {
                            "id": "c1",
                            "description": "Allow IoT",
                            "status": True,
                            "logStatus": True,
                        }
                    ],
                    "totalRows": 1,
                }
            },
            {"errorCode": 0},
        ]
    )

    await client.set_gateway_acl_status("site-id", "c1", enabled=False)

    post_call = client._authenticated_request.await_args_list[2]
    assert post_call.args == ("post", BATCH_EDIT_URL)
    assert post_call.kwargs["json_data"] == {
        "ids": ["c1"],
        "selectType": "include",
        "status": 0,
        "log": 1,
    }


@pytest.mark.asyncio
async def test_set_status_unknown_rule_raises_without_writing() -> None:
    """A rule that no longer exists raises OmadaApiError and writes nothing."""
    client = _client()
    client._authenticated_request = AsyncMock(
        side_effect=[
            PROFILE_MODE,
            {"result": {"data": [], "totalRows": 0}},
        ]
    )

    with pytest.raises(OmadaApiError):
        await client.set_gateway_acl_status("site-id", "gone", enabled=True)

    assert client._authenticated_request.await_count == 2
