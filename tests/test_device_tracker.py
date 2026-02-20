"""Tests for Omada device_tracker platform."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.omada_open_api.clients import process_client
from custom_components.omada_open_api.coordinator import OmadaClientCoordinator
from custom_components.omada_open_api.device_tracker import OmadaClientTracker

from .conftest import (
    SAMPLE_CLIENT_WIRED,
    SAMPLE_CLIENT_WIRELESS,
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
