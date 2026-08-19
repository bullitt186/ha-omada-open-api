"""Tests for SSID-based client filter in config/options flow (Issue #9)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from custom_components.omada_open_api.config_flow import (
    extract_ssids_from_clients,
    filter_clients_by_ssids,
)

if TYPE_CHECKING:
    pass

# Sample client data
WIRELESS_CLIENT_HOME = {
    "mac": "AA:BB:CC:DD:EE:01",
    "name": "Phone",
    "ip": "192.168.1.100",
    "active": True,
    "wireless": True,
    "ssid": "Home",
}

WIRELESS_CLIENT_IOT = {
    "mac": "AA:BB:CC:DD:EE:02",
    "name": "SmartBulb",
    "ip": "192.168.1.101",
    "active": True,
    "wireless": True,
    "ssid": "IoT",
}

WIRELESS_CLIENT_GUEST = {
    "mac": "AA:BB:CC:DD:EE:03",
    "name": "GuestPhone",
    "ip": "192.168.1.102",
    "active": True,
    "wireless": True,
    "ssid": "Guest",
}

WIRED_CLIENT = {
    "mac": "AA:BB:CC:DD:EE:04",
    "name": "Desktop",
    "ip": "192.168.1.103",
    "active": True,
    "wireless": False,
}

ALL_CLIENTS = [
    WIRELESS_CLIENT_HOME,
    WIRELESS_CLIENT_IOT,
    WIRELESS_CLIENT_GUEST,
    WIRED_CLIENT,
]


# ---------------------------------------------------------------------------
# Helper functions: extract_ssids_from_clients
# ---------------------------------------------------------------------------


def test_extract_ssids_returns_unique_ssids() -> None:
    """extract_ssids_from_clients returns sorted unique SSID list."""
    ssids = extract_ssids_from_clients(ALL_CLIENTS)
    assert "Home" in ssids
    assert "IoT" in ssids
    assert "Guest" in ssids
    assert len(set(ssids)) == len(ssids)  # No duplicates


def test_extract_ssids_excludes_wired_clients() -> None:
    """SSID extraction ignores wired clients with no ssid field."""
    ssids = extract_ssids_from_clients([WIRED_CLIENT])
    assert ssids == []


def test_extract_ssids_empty_list() -> None:
    """extract_ssids_from_clients returns empty list for empty input."""
    assert extract_ssids_from_clients([]) == []


def test_extract_ssids_sorted() -> None:
    """SSIDs are returned in alphabetical order."""
    ssids = extract_ssids_from_clients(ALL_CLIENTS)
    assert ssids == sorted(ssids)


# ---------------------------------------------------------------------------
# Helper functions: filter_clients_by_ssids
# ---------------------------------------------------------------------------


def test_filter_clients_by_ssid_returns_matching_wireless() -> None:
    """filter_clients_by_ssids returns only clients on selected SSIDs."""
    filtered = filter_clients_by_ssids(ALL_CLIENTS, ["Home"])
    macs = [c["mac"] for c in filtered]
    assert WIRELESS_CLIENT_HOME["mac"] in macs
    assert WIRELESS_CLIENT_IOT["mac"] not in macs
    assert WIRELESS_CLIENT_GUEST["mac"] not in macs


def test_filter_clients_always_includes_wired() -> None:
    """filter_clients_by_ssids always includes wired clients regardless of SSID filter."""
    filtered = filter_clients_by_ssids(ALL_CLIENTS, ["Home"])
    macs = [c["mac"] for c in filtered]
    assert WIRED_CLIENT["mac"] in macs


def test_filter_clients_empty_ssid_filter_returns_all() -> None:
    """Empty SSID filter returns all clients (no filtering)."""
    filtered = filter_clients_by_ssids(ALL_CLIENTS, [])
    assert len(filtered) == len(ALL_CLIENTS)


def test_filter_clients_multiple_ssids() -> None:
    """Multiple SSIDs selects clients from all specified SSIDs."""
    filtered = filter_clients_by_ssids(ALL_CLIENTS, ["Home", "IoT"])
    macs = [c["mac"] for c in filtered]
    assert WIRELESS_CLIENT_HOME["mac"] in macs
    assert WIRELESS_CLIENT_IOT["mac"] in macs
    assert WIRELESS_CLIENT_GUEST["mac"] not in macs
    assert WIRED_CLIENT["mac"] in macs  # wired always included


def test_filter_clients_unknown_ssid_returns_only_wired() -> None:
    """Filtering by unknown SSID returns only wired clients."""
    filtered = filter_clients_by_ssids(ALL_CLIENTS, ["UnknownSSID"])
    macs = [c["mac"] for c in filtered]
    assert WIRED_CLIENT["mac"] in macs
    assert len([c for c in filtered if c.get("wireless")]) == 0
