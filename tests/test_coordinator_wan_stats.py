"""Tests for WAN status fetching and OmadaDeviceStatsCoordinator."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.omada_open_api.api import OmadaApiError
from custom_components.omada_open_api.coordinator import (
    OmadaDeviceStatsCoordinator,
    OmadaSiteCoordinator,
)
from custom_components.omada_open_api.devices import process_device

from .conftest import (
    SAMPLE_DEVICE_AP,
    SAMPLE_DEVICE_GATEWAY,
    SAMPLE_DEVICE_SWITCH,
    SAMPLE_WAN_PORT_1,
    SAMPLE_WAN_PORT_2,
    TEST_SITE_ID,
    TEST_SITE_NAME,
)

# ---------------------------------------------------------------------------
# WAN status fetching in site coordinator
# ---------------------------------------------------------------------------


async def test_site_coordinator_fetches_wan_status(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test site coordinator fetches WAN status for gateways."""
    mock_api_client.get_gateway_wan_status = AsyncMock(
        return_value=[SAMPLE_WAN_PORT_1, SAMPLE_WAN_PORT_2]
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True

    wan = coordinator.data.get("wan_status", {})
    gw_mac = "AA-BB-CC-DD-EE-03"
    assert gw_mac in wan
    assert len(wan[gw_mac]) == 2
    assert wan[gw_mac][0]["portName"] == "WAN1"
    assert wan[gw_mac][1]["portName"] == "WAN2"


async def test_site_coordinator_wan_status_empty_when_no_gateways(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test WAN status empty when there are no gateway devices."""
    mock_api_client.get_devices = AsyncMock(
        return_value=[SAMPLE_DEVICE_AP, SAMPLE_DEVICE_SWITCH]
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True

    wan = coordinator.data.get("wan_status", {})
    assert wan == {}
    mock_api_client.get_gateway_wan_status.assert_not_called()


async def test_site_coordinator_wan_status_failure_graceful(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test WAN status failure doesn't break the coordinator update."""
    mock_api_client.get_gateway_wan_status = AsyncMock(
        side_effect=OmadaApiError("WAN fetch failed")
    )

    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coordinator.async_refresh()
    assert coordinator.last_update_success is True

    wan = coordinator.data.get("wan_status", {})
    gw_mac = "AA-BB-CC-DD-EE-03"
    # Gateway key is absent since fetch failed.
    assert gw_mac not in wan


# ---------------------------------------------------------------------------
# OmadaDeviceStatsCoordinator
# ---------------------------------------------------------------------------


async def test_device_stats_coordinator_fetches_daily_stats(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test device stats coordinator fetches daily traffic for all devices."""
    mock_api_client.get_device_stats = AsyncMock(
        return_value=[{"time": 1700000000, "tx": 500_000_000, "rx": 1_200_000_000}]
    )

    site_coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    # Populate site_coordinator.data with devices.
    site_coordinator.data = {
        "devices": {
            "AA-BB-CC-DD-EE-01": process_device(SAMPLE_DEVICE_AP),
            "AA-BB-CC-DD-EE-02": process_device(SAMPLE_DEVICE_SWITCH),
            "AA-BB-CC-DD-EE-03": process_device(SAMPLE_DEVICE_GATEWAY),
        },
        "poe_ports": {},
        "poe_budget": {},
        "site_id": TEST_SITE_ID,
        "site_name": TEST_SITE_NAME,
        "wan_status": {},
    }

    stats_coordinator = OmadaDeviceStatsCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_coordinator=site_coordinator,
    )

    await stats_coordinator.async_refresh()
    assert stats_coordinator.last_update_success is True

    data = stats_coordinator.data
    # APs are excluded — only switch and gateway get daily stats.
    assert len(data) == 2
    for mac in ("AA-BB-CC-DD-EE-02", "AA-BB-CC-DD-EE-03"):
        assert data[mac]["daily_tx"] == 500_000_000
        assert data[mac]["daily_rx"] == 1_200_000_000
    assert "AA-BB-CC-DD-EE-01" not in data  # AP skipped


async def test_device_stats_coordinator_empty_when_no_devices(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test device stats returns empty dict when no devices."""
    site_coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    site_coordinator.data = {
        "devices": {},
        "poe_ports": {},
        "poe_budget": {},
        "site_id": TEST_SITE_ID,
        "site_name": TEST_SITE_NAME,
        "wan_status": {},
    }

    stats_coordinator = OmadaDeviceStatsCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_coordinator=site_coordinator,
    )

    await stats_coordinator.async_refresh()
    assert stats_coordinator.last_update_success is True
    assert stats_coordinator.data == {}


async def test_device_stats_coordinator_partial_failure(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test device stats handles partial API failures gracefully."""
    call_count = 0

    async def _side_effect(*args: object, **kwargs: object) -> list:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise OmadaApiError("Device offline")
        return [{"time": 1700000000, "tx": 100, "rx": 200}]

    mock_api_client.get_device_stats = AsyncMock(side_effect=_side_effect)

    site_coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    site_coordinator.data = {
        "devices": {
            "AA-BB-CC-DD-EE-02": process_device(SAMPLE_DEVICE_SWITCH),
            "AA-BB-CC-DD-EE-03": process_device(SAMPLE_DEVICE_GATEWAY),
        },
        "poe_ports": {},
        "poe_budget": {},
        "site_id": TEST_SITE_ID,
        "site_name": TEST_SITE_NAME,
        "wan_status": {},
    }

    stats_coordinator = OmadaDeviceStatsCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_coordinator=site_coordinator,
    )

    await stats_coordinator.async_refresh()
    assert stats_coordinator.last_update_success is True

    data = stats_coordinator.data
    # One device failed, one succeeded — should have 1 entry.
    assert len(data) == 1


async def test_device_stats_coordinator_empty_when_site_data_none(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test device stats returns empty when site coordinator has no data."""
    site_coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    site_coordinator.data = None  # type: ignore[assignment]

    stats_coordinator = OmadaDeviceStatsCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_coordinator=site_coordinator,
    )

    await stats_coordinator.async_refresh()
    assert stats_coordinator.last_update_success is True
    assert stats_coordinator.data == {}


async def test_device_stats_coordinator_skips_unknown_device_type(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Test device stats skips devices with unknown type."""
    mock_api_client.get_device_stats = AsyncMock(
        return_value=[{"time": 1700000000, "tx": 100, "rx": 200}]
    )

    unknown_device = dict(SAMPLE_DEVICE_AP)
    unknown_device["type"] = "unknown"
    unknown_device["mac"] = "AA-BB-CC-DD-EE-99"

    site_coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    site_coordinator.data = {
        "devices": {
            "AA-BB-CC-DD-EE-99": process_device(unknown_device),
            "AA-BB-CC-DD-EE-02": process_device(SAMPLE_DEVICE_SWITCH),
        },
        "poe_ports": {},
        "poe_budget": {},
        "site_id": TEST_SITE_ID,
        "site_name": TEST_SITE_NAME,
        "wan_status": {},
    }

    stats_coordinator = OmadaDeviceStatsCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_coordinator=site_coordinator,
    )

    await stats_coordinator.async_refresh()
    assert stats_coordinator.last_update_success is True

    data = stats_coordinator.data
    # Only the switch should have stats; unknown and AP types are skipped.
    assert len(data) == 1
    assert "AA-BB-CC-DD-EE-02" in data
    assert "AA-BB-CC-DD-EE-99" not in data
