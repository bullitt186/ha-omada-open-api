"""Tests for device RX/TX activity rate sensors (Issue #8)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

from custom_components.omada_open_api.coordinator import OmadaSiteCoordinator
from custom_components.omada_open_api.sensor import DEVICE_SENSORS, OmadaDeviceSensor

from .conftest import TEST_SITE_ID, TEST_SITE_NAME

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

AP_MAC = "AA-BB-CC-DD-EE-01"
SWITCH_MAC = "AA-BB-CC-DD-EE-02"
GATEWAY_MAC = "AA-BB-CC-DD-EE-03"


def _make_coordinator(hass: HomeAssistant, devices: dict) -> OmadaSiteCoordinator:
    """Build a coordinator with the given device data."""
    coord = OmadaSiteCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    coord.data = {
        "devices": devices,
        "poe_ports": {},
        "poe_budget": {},
        "site_id": TEST_SITE_ID,
        "site_name": TEST_SITE_NAME,
    }
    return coord


def _make_device_sensor(
    hass: HomeAssistant, device_mac: str, devices: dict, desc_key: str
) -> OmadaDeviceSensor:
    """Create an OmadaDeviceSensor for the given device and description key."""
    coord = _make_coordinator(hass, devices)
    desc = next(d for d in DEVICE_SENSORS if d.key == desc_key)
    return OmadaDeviceSensor(coordinator=coord, description=desc, device_mac=device_mac)


# ---------------------------------------------------------------------------
# rx_activity sensor — devices with rx_rate_mbps
# ---------------------------------------------------------------------------


async def test_rx_activity_sensor_exists_in_device_sensors(hass: HomeAssistant) -> None:
    """DEVICE_SENSORS includes rx_activity and tx_activity descriptors."""
    keys = [d.key for d in DEVICE_SENSORS]
    assert "rx_activity" in keys
    assert "tx_activity" in keys


async def test_rx_activity_returns_value(hass: HomeAssistant) -> None:
    """rx_activity sensor returns rx_rate_mbps from device data."""
    device = {"mac": AP_MAC, "name": "AP", "type": "ap", "rx_rate_mbps": 12.5}
    sensor = _make_device_sensor(hass, AP_MAC, {AP_MAC: device}, "rx_activity")
    assert sensor.native_value == 12.5


async def test_tx_activity_returns_value(hass: HomeAssistant) -> None:
    """tx_activity sensor returns tx_rate_mbps from device data."""
    device = {"mac": AP_MAC, "name": "AP", "type": "ap", "tx_rate_mbps": 7.3}
    sensor = _make_device_sensor(hass, AP_MAC, {AP_MAC: device}, "tx_activity")
    assert sensor.native_value == 7.3


async def test_rx_activity_unavailable_when_no_rate(hass: HomeAssistant) -> None:
    """rx_activity is unavailable when rx_rate_mbps is not set."""
    device = {"mac": AP_MAC, "name": "AP", "type": "ap"}
    sensor = _make_device_sensor(hass, AP_MAC, {AP_MAC: device}, "rx_activity")
    assert sensor.available is False


async def test_tx_activity_unavailable_when_no_rate(hass: HomeAssistant) -> None:
    """tx_activity is unavailable when tx_rate_mbps is not set."""
    device = {"mac": AP_MAC, "name": "AP", "type": "ap"}
    sensor = _make_device_sensor(hass, AP_MAC, {AP_MAC: device}, "tx_activity")
    assert sensor.available is False


async def test_rx_activity_zero_rate(hass: HomeAssistant) -> None:
    """rx_activity is available and returns 0.0 when rx_rate_mbps is 0."""
    device = {"mac": AP_MAC, "name": "AP", "type": "ap", "rx_rate_mbps": 0.0}
    sensor = _make_device_sensor(hass, AP_MAC, {AP_MAC: device}, "rx_activity")
    assert sensor.available is True
    assert sensor.native_value == 0.0


# ---------------------------------------------------------------------------
# Coordinator: delta computation populates rx_rate_mbps / tx_rate_mbps
# ---------------------------------------------------------------------------


async def test_coordinator_computes_ap_rx_rate_on_second_poll(
    hass: HomeAssistant,
) -> None:
    """OmadaSiteCoordinator computes rx_rate_mbps from AP radio traffic deltas."""

    mock_api = MagicMock()
    mock_api.api_url = "https://api.example.com"
    mock_api.get_devices = AsyncMock(
        return_value=[
            {
                "mac": AP_MAC,
                "name": "AP",
                "type": "ap",
                "status": 14,
                "statusCategory": 1,
                "detailStatus": 14,
            }
        ]
    )
    mock_api.get_device_uplink_info = AsyncMock(return_value=[])
    mock_api.get_device_client_stats = AsyncMock(return_value=[])
    mock_api.get_site_ssids_comprehensive = AsyncMock(return_value=[])
    mock_api.get_ap_ssid_overrides = AsyncMock(return_value={"ssidOverrides": []})
    mock_api.get_poe_usage = AsyncMock(return_value=[])
    mock_api.get_switch_ports_poe = AsyncMock(return_value=[])
    mock_api.get_clients = AsyncMock(
        return_value={"data": [], "totalRows": 0, "currentPage": 1}
    )
    mock_api.get_gateway_wan_status = AsyncMock(return_value=[])
    mock_api.get_firmware_info = AsyncMock(return_value={})
    mock_api.get_switch_port_details = AsyncMock(return_value=[])
    mock_api.get_ap_radio_config = AsyncMock(return_value={})
    mock_api.get_wlan_optimization_status = AsyncMock(
        return_value={"status": 0, "beforeIndex": 55, "afterIndex": 80}
    )
    mock_api.get_gateway_info = AsyncMock(return_value={})

    # First poll: 100 MB RX total across bands
    first_radio_data = {
        "radioTraffic2g": {"rx": 80_000_000, "tx": 20_000_000},
        "radioTraffic5g": {"rx": 20_000_000, "tx": 5_000_000},
    }
    # Second poll: 110 MB RX total — 10 MB delta
    second_radio_data = {
        "radioTraffic2g": {"rx": 88_000_000, "tx": 22_000_000},
        "radioTraffic5g": {"rx": 22_000_000, "tx": 5_500_000},
    }
    mock_api.get_ap_radios = AsyncMock(
        side_effect=[first_radio_data, second_radio_data]
    )

    coord = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    # First poll — no rate (no previous data)
    data1 = await coord._async_update_data()  # noqa: SLF001
    # After first poll, rates should be None (no delta yet)
    assert data1["devices"][AP_MAC].get("rx_rate_mbps") is None

    # Force the radio util cache to expire so second poll fetches fresh data
    coord._last_radio_util_check = None  # noqa: SLF001

    # Second poll — rates should reflect delta
    data2 = await coord._async_update_data()  # noqa: SLF001
    rx_rate = data2["devices"][AP_MAC].get("rx_rate_mbps")
    assert rx_rate is not None
    assert rx_rate >= 0.0  # Must be non-negative


async def test_coordinator_resets_rate_on_counter_rollback(
    hass: HomeAssistant,
) -> None:
    """rx_rate_mbps is set to 0 when counters decrease (device reboot)."""

    mock_api = MagicMock()
    mock_api.api_url = "https://api.example.com"
    mock_api.get_devices = AsyncMock(
        return_value=[
            {
                "mac": AP_MAC,
                "name": "AP",
                "type": "ap",
                "status": 14,
                "statusCategory": 1,
                "detailStatus": 14,
            }
        ]
    )
    mock_api.get_device_uplink_info = AsyncMock(return_value=[])
    mock_api.get_device_client_stats = AsyncMock(return_value=[])
    mock_api.get_site_ssids_comprehensive = AsyncMock(return_value=[])
    mock_api.get_ap_ssid_overrides = AsyncMock(return_value={"ssidOverrides": []})
    mock_api.get_poe_usage = AsyncMock(return_value=[])
    mock_api.get_switch_ports_poe = AsyncMock(return_value=[])
    mock_api.get_clients = AsyncMock(
        return_value={"data": [], "totalRows": 0, "currentPage": 1}
    )
    mock_api.get_gateway_wan_status = AsyncMock(return_value=[])
    mock_api.get_firmware_info = AsyncMock(return_value={})
    mock_api.get_switch_port_details = AsyncMock(return_value=[])
    mock_api.get_ap_radio_config = AsyncMock(return_value={})
    mock_api.get_wlan_optimization_status = AsyncMock(
        return_value={"status": 0, "beforeIndex": 55, "afterIndex": 80}
    )
    mock_api.get_gateway_info = AsyncMock(return_value={})

    # First poll: high counters
    # Second poll: counters reset (device rebooted)
    mock_api.get_ap_radios = AsyncMock(
        side_effect=[
            {"radioTraffic2g": {"rx": 1_000_000_000, "tx": 500_000_000}},
            {"radioTraffic2g": {"rx": 1_000_000, "tx": 500_000}},  # reset
        ]
    )

    coord = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    await coord._async_update_data()  # noqa: SLF001  # first poll
    coord._last_radio_util_check = None  # noqa: SLF001  # force cache expiry
    data2 = await coord._async_update_data()  # noqa: SLF001  # second poll with rollback

    rx_rate = data2["devices"][AP_MAC].get("rx_rate_mbps", 0.0)
    assert rx_rate == 0.0  # Rollback → rate reset to 0
