"""Regression tests for currently open upstream issues."""

from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock

from custom_components.omada_open_api.api import OmadaApiClient, OmadaApiError
from custom_components.omada_open_api.clients import normalize_radio_band
from custom_components.omada_open_api.coordinator import OmadaSiteCoordinator
from custom_components.omada_open_api.devices import build_client_device_info
from custom_components.omada_open_api.const import DOMAIN


def test_normalize_radio_band_from_explicit_field_and_radio_id() -> None:
    """Client radio band is normalized for device tracker attributes."""
    assert normalize_radio_band({"radioBand": "2.4GHz"}) == "2.4 GHz"
    assert normalize_radio_band({"radioId": 1}) == "5 GHz"
    assert normalize_radio_band({"radioId": 3}) == "6 GHz"


def test_client_device_info_uses_via_device_id() -> None:
    """DeviceInfo uses the non-deprecated via_device_id field."""
    info = build_client_device_info(
        "AA-BB-CC-DD-EE-FF",
        {"name": "Phone"},
        "https://controller",
        via_device_id="device-registry-id",
    )
    assert info["identifiers"] == {(DOMAIN, "AA-BB-CC-DD-EE-FF")}
    assert info["via_device_id"] == "device-registry-id"
    assert "via_device" not in info


async def test_speed_test_ports_404_degrades_to_empty_list() -> None:
    """Non-Fusion controllers do not fail when the Fusion WAN endpoint is absent."""
    client = object.__new__(OmadaApiClient)
    client._api_url = "https://controller"
    client._omada_id = "omada"
    client._authenticated_request = AsyncMock(
        side_effect=OmadaApiError("HTTP 404", http_status=404)
    )

    result = await client.get_gateway_wan_speed_test_ports("site", "AA-BB")

    assert result == []


async def test_vpn_http_400_retries_with_fusion_filter() -> None:
    """HTTP 400 triggers the same Fusion filter fallback as API -1001."""
    client = object.__new__(OmadaApiClient)
    responses = [
        OmadaApiError("HTTP 400", http_status=400),
        {"errorCode": 0, "result": {"data": [], "totalRows": 0}},
    ]
    client._authenticated_request = AsyncMock(side_effect=responses)

    result = await client._get_paginated_vpn_rows(
        "https://controller/vpn",
        fusion_filter_fallback=True,
    )

    assert result == []
    second_call = client._authenticated_request.await_args_list[1]
    assert second_call.kwargs["params"]["filters.vpnType"] == 4


def test_ap_activity_rate_ignores_intermediate_flat_counter_poll() -> None:
    """Flat counters keep the prior rate until the stale window expires."""
    coordinator = object.__new__(OmadaSiteCoordinator)
    coordinator._prev_traffic = {}
    coordinator._normal_interval = dt.timedelta(seconds=60)
    devices = {"ap": {}}
    start = dt.datetime(2026, 10, 7, tzinfo=dt.UTC)

    coordinator._compute_and_store_rate(devices, "ap", 1_000_000, 1_000_000, start)
    coordinator._compute_and_store_rate(
        devices,
        "ap",
        2_000_000,
        1_500_000,
        start + dt.timedelta(seconds=60),
    )
    assert devices["ap"]["rx_rate_mbps"] == 0.0167
    assert devices["ap"]["tx_rate_mbps"] == 0.0083

    baseline = coordinator._prev_traffic["ap"]["ts"]
    coordinator._compute_and_store_rate(
        devices,
        "ap",
        2_000_000,
        1_500_000,
        start + dt.timedelta(seconds=120),
    )

    assert devices["ap"]["rx_rate_mbps"] == 0.0167
    assert devices["ap"]["tx_rate_mbps"] == 0.0083
    assert coordinator._prev_traffic["ap"]["ts"] == baseline

    coordinator._compute_and_store_rate(
        devices,
        "ap",
        2_000_000,
        1_500_000,
        start + dt.timedelta(seconds=300),
    )
    assert devices["ap"]["rx_rate_mbps"] == 0.0
    assert devices["ap"]["tx_rate_mbps"] == 0.0
