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
async def test_get_gateway_acls_custom_mode_reads_custom_endpoint() -> None:
    """Custom mode reads osg-custom-acls and returns the rows unchanged."""
    client = _client()
    row = {"id": "c1", "description": "Allow IoT", "status": True}
    client._authenticated_request = AsyncMock(
        side_effect=[CUSTOM_MODE, {"result": {"data": [row], "totalRows": 1}}]
    )

    rules = await client.get_gateway_acls("site-id")

    assert rules == [row]
    assert client._authenticated_request.await_args_list[1].args == ("get", CUSTOM_URL)


@pytest.mark.asyncio
async def test_get_gateway_acls_skips_rules_the_controller_cannot_read() -> None:
    """A controller 'General error' falls back to one-rule pages, skipping bad ones."""
    client = _client()
    general_error = OmadaApiError("General error.", error_code=-1)
    client._authenticated_request = AsyncMock(
        side_effect=[
            PROFILE_MODE,
            general_error,  # bulk read fails
            {"result": {"data": [{"id": "r1", "status": True}], "totalRows": 3}},
            general_error,  # rule 2 is unreadable
            {"result": {"data": [{"id": "r3", "status": False}], "totalRows": 3}},
        ]
    )

    rules = await client.get_gateway_acls("site-id")

    assert [r["id"] for r in rules] == ["r1", "r3"]
    calls = client._authenticated_request.await_args_list
    assert [c.kwargs["params"]["pageSize"] for c in calls[2:]] == [1, 1, 1]
    assert [c.kwargs["params"]["page"] for c in calls[2:]] == [1, 2, 3]


@pytest.mark.asyncio
async def test_get_gateway_acls_other_errors_are_not_retried_per_rule() -> None:
    """Errors other than the controller's -1 are raised without the fallback."""
    client = _client()
    client._authenticated_request = AsyncMock(
        side_effect=[PROFILE_MODE, OmadaApiError("denied", error_code=-1005)]
    )

    with pytest.raises(OmadaApiError):
        await client.get_gateway_acls("site-id")

    assert client._authenticated_request.await_count == 2


@pytest.mark.asyncio
async def test_get_gateway_acls_raises_when_no_rule_is_readable() -> None:
    """If every per-rule page fails the error is raised after a bounded retry."""
    client = _client()
    general_error = OmadaApiError("General error.", error_code=-1)
    client._authenticated_request = AsyncMock(
        side_effect=[PROFILE_MODE] + [general_error] * 60
    )

    with pytest.raises(OmadaApiError):
        await client.get_gateway_acls("site-id")

    assert client._authenticated_request.await_count <= 52


@pytest.mark.asyncio
async def test_set_status_profile_mode_writes_back_full_rule() -> None:
    """Profile mode PUTs the editable rule fields with only 'status' changed."""
    client = _client()
    rule = {
        "id": "acl-1",
        "index": 3,
        "description": "Block IoT",
        "status": True,
        "policy": 0,
    }
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
    # id and index are not part of the modify model, so they are not sent.
    assert put_call.kwargs["json_data"] == {
        "description": "Block IoT",
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

    # The rule list for the toggle comes from the custom-mode endpoint.
    assert client._authenticated_request.await_args_list[1].args == (
        "get",
        CUSTOM_URL,
    )
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


@pytest.mark.asyncio
async def test_config_mode_defaults_to_profile_when_result_is_incomplete() -> None:
    """A mode answer without 'mode' (or without 'result') means profile mode."""
    client = _client()
    client._authenticated_request = AsyncMock(
        side_effect=[{"result": {}}, {"errorCode": 0}]
    )

    assert await client.get_gateway_acl_config_mode("site-id") == 0
    assert await client.get_gateway_acl_config_mode("site-id") == 0


@pytest.mark.asyncio
async def test_get_gateway_acls_asks_mode_of_the_requested_site() -> None:
    """The config mode is read from the same site whose rules are listed."""
    client = _client()
    client._authenticated_request = AsyncMock(
        side_effect=[CUSTOM_MODE, {"result": {"data": [], "totalRows": 0}}]
    )

    await client.get_gateway_acls("other-site")

    calls = client._authenticated_request.await_args_list
    other = "https://controller.local/openapi/v1/controller-id/sites/other-site/acls"
    assert calls[0].args == ("get", f"{other}/osg-config-mode")
    assert calls[1].args == ("get", f"{other}/osg-custom-acls")


@pytest.mark.asyncio
async def test_rule_by_rule_fallback_requests_the_same_list_url() -> None:
    """The per-rule pages are GET requests to the list endpoint that failed."""
    client = _client()
    general_error = OmadaApiError("General error.", error_code=-1)
    client._authenticated_request = AsyncMock(
        side_effect=[
            PROFILE_MODE,
            general_error,
            {"result": {"data": [{"id": "r1"}], "totalRows": 1}},
        ]
    )

    await client.get_gateway_acls("site-id")

    fallback = client._authenticated_request.await_args_list[2]
    assert fallback.args == ("get", PROFILE_URL)
    assert fallback.kwargs["params"] == {"page": 1, "pageSize": 1}


@pytest.mark.asyncio
async def test_rule_by_rule_fallback_tolerates_missing_payload_fields() -> None:
    """An answer without result, data or totalRows yields no rules, not a crash."""
    client = _client()
    general_error = OmadaApiError("General error.", error_code=-1)
    client._authenticated_request = AsyncMock(
        side_effect=[PROFILE_MODE, general_error, {"errorCode": 0}]
    )

    assert await client.get_gateway_acls("site-id") == []


@pytest.mark.asyncio
async def test_rule_by_rule_fallback_reads_every_page_up_to_total_rows() -> None:
    """With totalRows=3 exactly pages 1 to 3 are requested, no more."""
    client = _client()
    general_error = OmadaApiError("General error.", error_code=-1)
    pages = [{"result": {"data": [{"id": f"r{i}"}], "totalRows": 3}} for i in (1, 2, 3)]
    client._authenticated_request = AsyncMock(
        side_effect=[PROFILE_MODE, general_error, *pages]
    )

    rules = await client.get_gateway_acls("site-id")

    assert [r["id"] for r in rules] == ["r1", "r2", "r3"]
    requested = [
        c.kwargs["params"]["page"]
        for c in client._authenticated_request.await_args_list[2:]
    ]
    assert requested == [1, 2, 3]


@pytest.mark.asyncio
async def test_set_status_asks_mode_and_rules_of_the_requested_site() -> None:
    """Mode lookup and rule list use the site that is being changed."""
    client = _client()
    client._authenticated_request = AsyncMock(
        side_effect=[
            PROFILE_MODE,
            {"result": {"data": [{"id": "a", "status": True}], "totalRows": 1}},
            {"errorCode": 0},
        ]
    )

    await client.set_gateway_acl_status("other-site", "a", enabled=True)

    other = "https://controller.local/openapi/v1/controller-id/sites/other-site/acls"
    calls = client._authenticated_request.await_args_list
    assert calls[0].args == ("get", f"{other}/osg-config-mode")
    assert calls[1].args == ("get", f"{other}/osg-acls")
    assert calls[2].args == ("put", f"{other}/osg-acls/a")


@pytest.mark.asyncio
async def test_set_status_unknown_rule_error_names_rule_and_site() -> None:
    """The error for a vanished rule says which rule in which site."""
    client = _client()
    client._authenticated_request = AsyncMock(
        side_effect=[PROFILE_MODE, {"result": {"data": [], "totalRows": 0}}]
    )

    with pytest.raises(OmadaApiError, match=r"gone.*site-id"):
        await client.set_gateway_acl_status("site-id", "gone", enabled=True)
