"""Tests for Omada device_tracker platform."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from homeassistant.components.device_tracker import SourceType

from custom_components.omada_open_api.clients import process_client
from custom_components.omada_open_api.coordinator import (
    OmadaClientCoordinator,
    OmadaSiteCoordinator,
)
from custom_components.omada_open_api.device_tracker import (
    OmadaClientTracker,
    OmadaDeviceTracker,
)
from custom_components.omada_open_api.devices import process_device

from .conftest import (
    SAMPLE_CLIENT_WIRED,
    SAMPLE_CLIENT_WIRELESS,
    SAMPLE_DEVICE_AP,
    SAMPLE_DEVICE_GATEWAY,
    SAMPLE_DEVICE_SWITCH,
    TEST_SITE_ID,
    TEST_SITE_NAME,
)

WIRELESS_MAC = "11-22-33-44-55-AA"
WIRED_MAC = "11-22-33-44-55-BB"


def _build_coordinator(
    hass: HomeAssistant,
    clients: dict[str, dict] | None = None,
) -> OmadaClientCoordinator:
    """Create a client coordinator with mock data."""
    coordinator = OmadaClientCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=[WIRELESS_MAC, WIRED_MAC],
    )
    coordinator.data = clients or {}
    return coordinator


def _create_tracker(
    hass: HomeAssistant,
    client_mac: str,
    clients: dict[str, dict],
) -> OmadaClientTracker:
    """Create an OmadaClientTracker entity."""
    coordinator = _build_coordinator(hass, clients)
    return OmadaClientTracker(coordinator=coordinator, client_mac=client_mac)


# ---------------------------------------------------------------------------
# is_connected
# ---------------------------------------------------------------------------


async def test_is_connected_wireless_active(hass: HomeAssistant) -> None:
    """Test wireless client shows as connected."""
    data = process_client(SAMPLE_CLIENT_WIRELESS)
    tracker = _create_tracker(hass, WIRELESS_MAC, {WIRELESS_MAC: data})
    assert tracker.is_connected is True


async def test_is_connected_wired_active(hass: HomeAssistant) -> None:
    """Test wired client shows as connected."""
    data = process_client(SAMPLE_CLIENT_WIRED)
    tracker = _create_tracker(hass, WIRED_MAC, {WIRED_MAC: data})
    assert tracker.is_connected is True


async def test_is_connected_inactive(hass: HomeAssistant) -> None:
    """Test inactive client shows as not connected."""
    raw = dict(SAMPLE_CLIENT_WIRELESS)
    raw["active"] = False
    data = process_client(raw)
    tracker = _create_tracker(hass, WIRELESS_MAC, {WIRELESS_MAC: data})
    assert tracker.is_connected is False


async def test_is_connected_missing_client(hass: HomeAssistant) -> None:
    """Test missing client returns False."""
    tracker = _create_tracker(hass, WIRELESS_MAC, {})
    assert tracker.is_connected is False


# ---------------------------------------------------------------------------
# ip_address
# ---------------------------------------------------------------------------


async def test_ip_address(hass: HomeAssistant) -> None:
    """Test IP address returned for active client."""
    data = process_client(SAMPLE_CLIENT_WIRELESS)
    tracker = _create_tracker(hass, WIRELESS_MAC, {WIRELESS_MAC: data})
    assert tracker.ip_address == "192.168.1.100"


async def test_ip_address_missing_client(hass: HomeAssistant) -> None:
    """Test IP address returns None when client not in data."""
    tracker = _create_tracker(hass, WIRELESS_MAC, {})
    assert tracker.ip_address is None


# ---------------------------------------------------------------------------
# hostname
# ---------------------------------------------------------------------------


async def test_hostname(hass: HomeAssistant) -> None:
    """Test hostname returned for client."""
    data = process_client(SAMPLE_CLIENT_WIRELESS)
    tracker = _create_tracker(hass, WIRELESS_MAC, {WIRELESS_MAC: data})
    assert tracker.hostname == "phone-host"


async def test_hostname_wired(hass: HomeAssistant) -> None:
    """Test hostname returned for wired client."""
    data = process_client(SAMPLE_CLIENT_WIRED)
    tracker = _create_tracker(hass, WIRED_MAC, {WIRED_MAC: data})
    assert tracker.hostname == "desktop-host"


async def test_hostname_missing_client(hass: HomeAssistant) -> None:
    """Test hostname returns None when client not in data."""
    tracker = _create_tracker(hass, WIRELESS_MAC, {})
    assert tracker.hostname is None


# ---------------------------------------------------------------------------
# mac_address
# ---------------------------------------------------------------------------


async def test_mac_address_normalized(hass: HomeAssistant) -> None:
    """Test MAC address is normalized to colon-separated lowercase."""
    data = process_client(SAMPLE_CLIENT_WIRELESS)
    tracker = _create_tracker(hass, WIRELESS_MAC, {WIRELESS_MAC: data})
    assert tracker.mac_address == "11:22:33:44:55:aa"


# ---------------------------------------------------------------------------
# unique_id
# ---------------------------------------------------------------------------


async def test_unique_id(hass: HomeAssistant) -> None:
    """Test unique ID format."""
    data = process_client(SAMPLE_CLIENT_WIRELESS)
    tracker = _create_tracker(hass, WIRELESS_MAC, {WIRELESS_MAC: data})
    assert tracker.unique_id == f"omada_open_api_{WIRELESS_MAC}"


# ---------------------------------------------------------------------------
# name
# ---------------------------------------------------------------------------


async def test_name_from_client_name(hass: HomeAssistant) -> None:
    """Test entity name comes from client name."""
    data = process_client(SAMPLE_CLIENT_WIRELESS)
    tracker = _create_tracker(hass, WIRELESS_MAC, {WIRELESS_MAC: data})
    assert tracker.name == "Phone"


async def test_name_fallback_to_hostname(hass: HomeAssistant) -> None:
    """Test entity name falls back to hostname when name absent."""
    raw = dict(SAMPLE_CLIENT_WIRELESS)
    raw["name"] = None
    data = process_client(raw)
    tracker = _create_tracker(hass, WIRELESS_MAC, {WIRELESS_MAC: data})
    assert tracker.name == "phone-host"


async def test_name_fallback_to_mac(hass: HomeAssistant) -> None:
    """Test entity name falls back to MAC when name and hostname absent."""
    raw = dict(SAMPLE_CLIENT_WIRELESS)
    raw["name"] = None
    raw["hostName"] = None
    data = process_client(raw)
    tracker = _create_tracker(hass, WIRELESS_MAC, {WIRELESS_MAC: data})
    # process_client returns "Unknown" when both name and hostName are None.
    # device_tracker uses that as the name.
    assert tracker.name == "Unknown"


# ---------------------------------------------------------------------------
# extra_state_attributes
# ---------------------------------------------------------------------------


async def test_extra_attrs_wireless(hass: HomeAssistant) -> None:
    """Test extra attributes for wireless client."""
    data = process_client(SAMPLE_CLIENT_WIRELESS)
    tracker = _create_tracker(hass, WIRELESS_MAC, {WIRELESS_MAC: data})
    attrs = tracker.extra_state_attributes
    assert attrs["ssid"] == "MyWiFi"
    assert attrs["connected_ap"] == "Office AP"
    assert attrs["connection_type"] == "wireless"
    assert "connected_switch" not in attrs


async def test_extra_attrs_wired(hass: HomeAssistant) -> None:
    """Test extra attributes for wired client."""
    data = process_client(SAMPLE_CLIENT_WIRED)
    tracker = _create_tracker(hass, WIRED_MAC, {WIRED_MAC: data})
    attrs = tracker.extra_state_attributes
    assert attrs["connected_switch"] == "Core Switch"
    assert attrs["connection_type"] == "wired"
    assert "ssid" not in attrs
    assert "connected_ap" not in attrs


async def test_extra_attrs_missing_client(hass: HomeAssistant) -> None:
    """Test extra attributes returns empty dict for missing client."""
    tracker = _create_tracker(hass, WIRELESS_MAC, {})
    assert tracker.extra_state_attributes == {}


# ---------------------------------------------------------------------------
# Coordinator interaction
# ---------------------------------------------------------------------------


async def test_tracker_reflects_state_change(hass: HomeAssistant) -> None:
    """Test tracker updates when coordinator data changes."""
    data = process_client(SAMPLE_CLIENT_WIRELESS)
    coordinator = _build_coordinator(hass, {WIRELESS_MAC: data})
    tracker = OmadaClientTracker(coordinator=coordinator, client_mac=WIRELESS_MAC)

    assert tracker.is_connected is True

    # Simulate client going offline.
    offline = dict(data)
    offline["active"] = False
    coordinator.data = {WIRELESS_MAC: offline}

    assert tracker.is_connected is False


async def test_tracker_coordinator_failure(hass: HomeAssistant) -> None:
    """Test tracker reflects coordinator failure."""
    data = process_client(SAMPLE_CLIENT_WIRELESS)
    tracker = _create_tracker(hass, WIRELESS_MAC, {WIRELESS_MAC: data})
    tracker.coordinator.last_update_success = False
    assert tracker.available is False


# ===========================================================================
# OmadaDeviceTracker tests (AP / switch / gateway presence)
# ===========================================================================

AP_MAC = "AA-BB-CC-DD-EE-01"
SWITCH_MAC = "AA-BB-CC-DD-EE-02"
GATEWAY_MAC = "AA-BB-CC-DD-EE-03"


def _build_site_coordinator(
    hass: HomeAssistant,
    devices: dict[str, dict[str, Any]] | None = None,
) -> OmadaSiteCoordinator:
    """Create a site coordinator with mock device data."""
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    coordinator.data = {
        "devices": devices or {},
        "poe_budget": {},
        "poe_ports": {},
        "site_id": TEST_SITE_ID,
        "site_name": TEST_SITE_NAME,
    }
    return coordinator


def _create_device_tracker(
    hass: HomeAssistant,
    device_mac: str,
    devices: dict[str, dict[str, Any]],
) -> OmadaDeviceTracker:
    """Create an OmadaDeviceTracker entity."""
    coordinator = _build_site_coordinator(hass, devices)
    return OmadaDeviceTracker(coordinator=coordinator, device_mac=device_mac)


def _connected_device(raw: dict[str, Any]) -> dict[str, Any]:
    """Process a device and ensure status=14 (connected)."""
    return process_device(raw)


def _disconnected_device(raw: dict[str, Any]) -> dict[str, Any]:
    """Process a device with status=0 (disconnected)."""
    modified = dict(raw)
    modified["status"] = 0
    return process_device(modified)


# ---------------------------------------------------------------------------
# is_connected (device)
# ---------------------------------------------------------------------------


async def test_device_tracker_ap_connected(hass: HomeAssistant) -> None:
    """Test AP device tracker shows as connected."""
    data = _connected_device(SAMPLE_DEVICE_AP)
    tracker = _create_device_tracker(hass, AP_MAC, {AP_MAC: data})
    assert tracker.is_connected is True


async def test_device_tracker_switch_connected(hass: HomeAssistant) -> None:
    """Test switch device tracker shows as connected."""
    data = _connected_device(SAMPLE_DEVICE_SWITCH)
    tracker = _create_device_tracker(hass, SWITCH_MAC, {SWITCH_MAC: data})
    assert tracker.is_connected is True


async def test_device_tracker_gateway_connected(hass: HomeAssistant) -> None:
    """Test gateway device tracker shows as connected."""
    data = _connected_device(SAMPLE_DEVICE_GATEWAY)
    tracker = _create_device_tracker(hass, GATEWAY_MAC, {GATEWAY_MAC: data})
    assert tracker.is_connected is True


async def test_device_tracker_disconnected(hass: HomeAssistant) -> None:
    """Test device tracker shows as disconnected."""
    data = _disconnected_device(SAMPLE_DEVICE_AP)
    tracker = _create_device_tracker(hass, AP_MAC, {AP_MAC: data})
    assert tracker.is_connected is False


async def test_device_tracker_missing_device(hass: HomeAssistant) -> None:
    """Test missing device returns False."""
    tracker = _create_device_tracker(hass, AP_MAC, {})
    assert tracker.is_connected is False


# ---------------------------------------------------------------------------
# source_type
# ---------------------------------------------------------------------------


async def test_device_tracker_source_type(hass: HomeAssistant) -> None:
    """Test device tracker source type is ROUTER."""
    data = _connected_device(SAMPLE_DEVICE_AP)
    tracker = _create_device_tracker(hass, AP_MAC, {AP_MAC: data})
    assert tracker.source_type == SourceType.ROUTER


# ---------------------------------------------------------------------------
# unique_id
# ---------------------------------------------------------------------------


async def test_device_tracker_unique_id(hass: HomeAssistant) -> None:
    """Test unique ID format for device tracker."""
    data = _connected_device(SAMPLE_DEVICE_AP)
    tracker = _create_device_tracker(hass, AP_MAC, {AP_MAC: data})
    assert tracker.unique_id == f"omada_open_api_device_{AP_MAC}"


# ---------------------------------------------------------------------------
# mac_address
# ---------------------------------------------------------------------------


async def test_device_tracker_mac_normalized(hass: HomeAssistant) -> None:
    """Test MAC address is normalized to colon-separated lowercase."""
    data = _connected_device(SAMPLE_DEVICE_AP)
    tracker = _create_device_tracker(hass, AP_MAC, {AP_MAC: data})
    assert tracker.mac_address == "aa:bb:cc:dd:ee:01"


# ---------------------------------------------------------------------------
# ip_address
# ---------------------------------------------------------------------------


async def test_device_tracker_ip_address(hass: HomeAssistant) -> None:
    """Test IP address returned for device."""
    data = _connected_device(SAMPLE_DEVICE_AP)
    tracker = _create_device_tracker(hass, AP_MAC, {AP_MAC: data})
    assert tracker.ip_address == "192.168.1.10"


async def test_device_tracker_ip_missing(hass: HomeAssistant) -> None:
    """Test IP address returns None when device not in data."""
    tracker = _create_device_tracker(hass, AP_MAC, {})
    assert tracker.ip_address is None


# ---------------------------------------------------------------------------
# hostname
# ---------------------------------------------------------------------------


async def test_device_tracker_hostname(hass: HomeAssistant) -> None:
    """Test hostname returns device name."""
    data = _connected_device(SAMPLE_DEVICE_AP)
    tracker = _create_device_tracker(hass, AP_MAC, {AP_MAC: data})
    assert tracker.hostname == "Office AP"


async def test_device_tracker_hostname_missing(hass: HomeAssistant) -> None:
    """Test hostname returns None when device not in data."""
    tracker = _create_device_tracker(hass, AP_MAC, {})
    assert tracker.hostname is None


# ---------------------------------------------------------------------------
# name
# ---------------------------------------------------------------------------


async def test_device_tracker_name(hass: HomeAssistant) -> None:
    """Test entity name comes from device name."""
    data = _connected_device(SAMPLE_DEVICE_AP)
    tracker = _create_device_tracker(hass, AP_MAC, {AP_MAC: data})
    assert tracker.name == "Office AP"


# ---------------------------------------------------------------------------
# extra_state_attributes
# ---------------------------------------------------------------------------


async def test_device_tracker_attrs_ap(hass: HomeAssistant) -> None:
    """Test extra attributes for an AP device tracker."""
    data = _connected_device(SAMPLE_DEVICE_AP)
    tracker = _create_device_tracker(hass, AP_MAC, {AP_MAC: data})
    attrs = tracker.extra_state_attributes
    assert attrs["device_type"] == "ap"
    assert attrs["model"] == "EAP660 HD"
    assert attrs["firmware_version"] == "1.2.3"
    assert attrs["ip_address"] == "192.168.1.10"
    assert attrs["detail_status"] == "Connected"


async def test_device_tracker_attrs_switch(hass: HomeAssistant) -> None:
    """Test extra attributes for a switch device tracker."""
    data = _connected_device(SAMPLE_DEVICE_SWITCH)
    tracker = _create_device_tracker(hass, SWITCH_MAC, {SWITCH_MAC: data})
    attrs = tracker.extra_state_attributes
    assert attrs["device_type"] == "switch"
    assert attrs["model"] == "TL-SG3428X"


async def test_device_tracker_attrs_gateway(hass: HomeAssistant) -> None:
    """Test extra attributes for a gateway device tracker."""
    data = _connected_device(SAMPLE_DEVICE_GATEWAY)
    tracker = _create_device_tracker(hass, GATEWAY_MAC, {GATEWAY_MAC: data})
    attrs = tracker.extra_state_attributes
    assert attrs["device_type"] == "gateway"
    assert attrs["model"] == "ER8411"


async def test_device_tracker_attrs_missing(hass: HomeAssistant) -> None:
    """Test extra attributes returns empty dict for missing device."""
    tracker = _create_device_tracker(hass, AP_MAC, {})
    assert tracker.extra_state_attributes == {}


# ---------------------------------------------------------------------------
# device_info
# ---------------------------------------------------------------------------


async def test_device_tracker_device_info(hass: HomeAssistant) -> None:
    """Test device info links tracker to correct device."""
    data = _connected_device(SAMPLE_DEVICE_AP)
    tracker = _create_device_tracker(hass, AP_MAC, {AP_MAC: data})
    info = tracker._attr_device_info  # noqa: SLF001
    assert info is not None
    assert info["identifiers"] == {("omada_open_api", AP_MAC)}
    assert info["name"] == "Office AP"
    assert info["manufacturer"] == "TP-Link"
    assert info["model"] == "EAP660 HD"
    assert info["sw_version"] == "1.2.3"


async def test_device_tracker_device_info_missing(hass: HomeAssistant) -> None:
    """Test device info returns None when device not in data."""
    tracker = _create_device_tracker(hass, AP_MAC, {})
    assert (
        not hasattr(tracker, "_attr_device_info") or tracker._attr_device_info is None  # noqa: SLF001
    )


# ---------------------------------------------------------------------------
# Coordinator interaction (device)
# ---------------------------------------------------------------------------


async def test_device_tracker_reflects_state_change(hass: HomeAssistant) -> None:
    """Test device tracker updates when coordinator data changes."""
    data = _connected_device(SAMPLE_DEVICE_AP)
    coordinator = _build_site_coordinator(hass, {AP_MAC: data})
    tracker = OmadaDeviceTracker(coordinator=coordinator, device_mac=AP_MAC)
    assert tracker.is_connected is True

    # Simulate device going offline.
    offline = dict(data)
    offline["status"] = 0
    coordinator.data["devices"] = {AP_MAC: offline}
    assert tracker.is_connected is False


async def test_device_tracker_coordinator_failure(hass: HomeAssistant) -> None:
    """Test device tracker reflects coordinator failure."""
    data = _connected_device(SAMPLE_DEVICE_AP)
    tracker = _create_device_tracker(hass, AP_MAC, {AP_MAC: data})
    tracker.coordinator.last_update_success = False
    assert tracker.available is False
