"""Tests for OmadaSiteCoordinator._assign_clients_to_devices."""

from __future__ import annotations

from typing import Any

from custom_components.omada_open_api.coordinator import OmadaSiteCoordinator


def _make_clients() -> list[dict[str, Any]]:
    """Return sample client list."""
    return [
        {
            "name": "WiFi Laptop",
            "mac": "CC:00:00:00:00:01",
            "ip": "10.0.0.1",
            "wireless": True,
            "ap_mac": "AP-MAC-01",
            "switch_mac": None,
            "gateway_mac": None,
        },
        {
            "name": "Wired Desktop",
            "mac": "CC:00:00:00:00:02",
            "ip": "10.0.0.2",
            "wireless": False,
            "ap_mac": None,
            "switch_mac": "SW-MAC-01",
            "gateway_mac": None,
        },
        {
            "name": "Gateway Client",
            "mac": "CC:00:00:00:00:03",
            "ip": "10.0.0.3",
            "wireless": False,
            "ap_mac": None,
            "switch_mac": None,
            "gateway_mac": "GW-MAC-01",
        },
        {
            "name": "Orphan Client",
            "mac": "CC:00:00:00:00:04",
            "ip": "10.0.0.4",
            "wireless": False,
            "ap_mac": None,
            "switch_mac": None,
            "gateway_mac": None,
        },
    ]


def _make_devices() -> dict[str, dict[str, Any]]:
    """Return sample device dict."""
    return {
        "AP-MAC-01": {"name": "Office AP", "type": "ap"},
        "SW-MAC-01": {"name": "Core Switch", "type": "switch"},
        "GW-MAC-01": {"name": "Main Gateway", "type": "gateway"},
    }


def test_assign_clients_basic() -> None:
    """Test basic client-to-device assignment."""
    devices = _make_devices()
    clients = _make_clients()

    OmadaSiteCoordinator._assign_clients_to_devices(devices, clients)  # noqa: SLF001

    assert len(devices["AP-MAC-01"]["connected_clients"]) == 1
    assert devices["AP-MAC-01"]["connected_clients"][0]["name"] == "WiFi Laptop"

    assert len(devices["SW-MAC-01"]["connected_clients"]) == 1
    assert devices["SW-MAC-01"]["connected_clients"][0]["name"] == "Wired Desktop"

    assert len(devices["GW-MAC-01"]["connected_clients"]) == 1
    assert devices["GW-MAC-01"]["connected_clients"][0]["name"] == "Gateway Client"


def test_assign_clients_orphan_not_added() -> None:
    """Test that a client with no device MAC is not assigned anywhere."""
    devices = _make_devices()
    clients = _make_clients()

    OmadaSiteCoordinator._assign_clients_to_devices(devices, clients)  # noqa: SLF001

    total = sum(len(d["connected_clients"]) for d in devices.values())
    assert total == 3  # Orphan excluded


def test_assign_clients_empty() -> None:
    """Test assignment with empty client list."""
    devices = _make_devices()

    OmadaSiteCoordinator._assign_clients_to_devices(devices, [])  # noqa: SLF001

    for dev in devices.values():
        assert dev["connected_clients"] == []


def test_assign_clients_unknown_device() -> None:
    """Test that clients with unknown parent MACs are skipped."""
    devices = _make_devices()
    clients = [
        {
            "name": "Unknown Parent",
            "mac": "CC:00:00:00:00:FF",
            "ip": "10.0.0.99",
            "wireless": True,
            "ap_mac": "UNKNOWN-AP",
            "switch_mac": None,
            "gateway_mac": None,
        },
    ]

    OmadaSiteCoordinator._assign_clients_to_devices(devices, clients)  # noqa: SLF001

    total = sum(len(d["connected_clients"]) for d in devices.values())
    assert total == 0


def test_assign_clients_wireless_prefers_ap() -> None:
    """Test wireless client with ap_mac goes to AP, not switch."""
    devices = _make_devices()
    clients = [
        {
            "name": "Dual Client",
            "mac": "CC:00:00:00:00:DD",
            "ip": "10.0.0.55",
            "wireless": True,
            "ap_mac": "AP-MAC-01",
            "switch_mac": "SW-MAC-01",
            "gateway_mac": None,
        },
    ]

    OmadaSiteCoordinator._assign_clients_to_devices(devices, clients)  # noqa: SLF001

    assert len(devices["AP-MAC-01"]["connected_clients"]) == 1
    assert len(devices["SW-MAC-01"]["connected_clients"]) == 0
