"""Tests for gateway ACL (osg-acls) API access."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.omada_open_api.api import OmadaApiClient, OmadaApiError

BASE = "https://controller.local/openapi/v1/controller-id/sites/site-id/acls/osg-acls"


def _client() -> OmadaApiClient:
    """Build a client without running __init__ (no HA session needed)."""
    client = OmadaApiClient.__new__(OmadaApiClient)
    client._api_url = "https://controller.local"
    client._omada_id = "controller-id"
    return client


@pytest.mark.asyncio
async def test_get_gateway_acls_paginates_all_rows() -> None:
    """All pages are fetched using totalRows until every rule is collected."""
    client = _client()
    first_page = [{"id": f"a{i}", "status": True} for i in range(100)]
    second_page = [{"id": "last", "status": False}]
    client._authenticated_request = AsyncMock(
        side_effect=[
            {"result": {"data": first_page, "totalRows": 101}},
            {"result": {"data": second_page, "totalRows": 101}},
        ]
    )

    rules = await client.get_gateway_acls("site-id")

    assert len(rules) == 101
    assert rules[-1]["id"] == "last"
    calls = client._authenticated_request.await_args_list
    assert calls[0].args == ("get", BASE)
    assert calls[0].kwargs["params"] == {"page": 1, "pageSize": 100}
    assert calls[1].kwargs["params"] == {"page": 2, "pageSize": 100}


@pytest.mark.asyncio
async def test_set_gateway_acl_status_writes_back_full_rule() -> None:
    """The PUT carries the complete rule with only 'status' changed."""
    client = _client()
    rule = {"id": "acl-1", "name": "Block IoT", "status": True, "policy": 0}
    client._authenticated_request = AsyncMock(
        side_effect=[
            {"result": {"data": [rule], "totalRows": 1}},
            {"errorCode": 0},
        ]
    )

    await client.set_gateway_acl_status("site-id", "acl-1", enabled=False)

    put_call = client._authenticated_request.await_args_list[1]
    assert put_call.args == ("put", f"{BASE}/acl-1")
    assert put_call.kwargs["json_data"] == {
        "id": "acl-1",
        "name": "Block IoT",
        "status": False,
        "policy": 0,
    }
    # The cached/list rule must not be mutated.
    assert rule["status"] is True


@pytest.mark.asyncio
async def test_set_gateway_acl_status_unknown_rule_raises() -> None:
    """A rule that no longer exists raises OmadaApiError and writes nothing."""
    client = _client()
    client._authenticated_request = AsyncMock(
        return_value={"result": {"data": [], "totalRows": 0}}
    )

    with pytest.raises(OmadaApiError):
        await client.set_gateway_acl_status("site-id", "gone", enabled=True)

    assert client._authenticated_request.await_count == 1
