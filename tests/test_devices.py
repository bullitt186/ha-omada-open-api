"""Tests for Omada device helpers."""

from __future__ import annotations

from custom_components.omada_open_api.devices import (
    format_detail_status,
    format_link_speed,
    get_device_sort_key,
    parse_uptime,
    process_device,
)

# ---------------------------------------------------------------------------
# parse_uptime
# ---------------------------------------------------------------------------


def test_parse_uptime_none() -> None:
    """Test parse_uptime with None input."""
    assert parse_uptime(None) is None


def test_parse_uptime_int() -> None:
    """Test parse_uptime with integer input."""
    assert parse_uptime(3600) == 3600


def test_parse_uptime_string_full() -> None:
    """Test parse_uptime with full day/hour/min/sec string."""
    assert parse_uptime("4day(s) 17h 26m 57s") == 4 * 86400 + 17 * 3600 + 26 * 60 + 57


def test_parse_uptime_string_hours_only() -> None:
    """Test parse_uptime with hours-only string."""
    assert parse_uptime("5h 0m 0s") == 5 * 3600


def test_parse_uptime_unparseable() -> None:
    """Test parse_uptime with unparseable string returns None."""
    assert parse_uptime("no match here") is None


# ---------------------------------------------------------------------------
# format_link_speed
# ---------------------------------------------------------------------------


def test_format_link_speed_none() -> None:
    """Test format_link_speed with None input."""
    assert format_link_speed(None) is None


def test_format_link_speed_known_values() -> None:
    """Test format_link_speed with known speed codes."""
    assert format_link_speed(0) == "Auto"
    assert format_link_speed(1) == "10 Mbps"
    assert format_link_speed(2) == "100 Mbps"
    assert format_link_speed(3) == "1 Gbps"
    assert format_link_speed(4) == "2.5 Gbps"
    assert format_link_speed(5) == "10 Gbps"
    assert format_link_speed(6) == "5 Gbps"
    assert format_link_speed(7) == "25 Gbps"
    assert format_link_speed(8) == "100 Gbps"


def test_format_link_speed_unknown() -> None:
    """Test format_link_speed with unknown code."""
    assert format_link_speed(99) == "Unknown (99)"


# ---------------------------------------------------------------------------
# format_detail_status
# ---------------------------------------------------------------------------


def test_format_detail_status_none() -> None:
    """Test format_detail_status with None input."""
    assert format_detail_status(None) is None


def test_format_detail_status_known() -> None:
    """Test format_detail_status with known codes."""
    assert format_detail_status(14) == "Connected"
    assert format_detail_status(0) == "Disconnected"


def test_format_detail_status_unknown() -> None:
    """Test format_detail_status with unknown code."""
    assert format_detail_status(999) == "Unknown (999)"


# ---------------------------------------------------------------------------
# get_device_sort_key
# ---------------------------------------------------------------------------


def test_device_sort_key_gateway() -> None:
    """Test that gateways sort first."""
    key = get_device_sort_key({"type": "gateway"}, "AA")
    assert key[0] == 0


def test_device_sort_key_switch() -> None:
    """Test that switches sort second."""
    key = get_device_sort_key({"type": "switch"}, "BB")
    assert key[0] == 1


def test_device_sort_key_ap() -> None:
    """Test that APs sort third."""
    key = get_device_sort_key({"type": "ap"}, "CC")
    assert key[0] == 2


# ---------------------------------------------------------------------------
# process_device
# ---------------------------------------------------------------------------


def test_process_device_minimal() -> None:
    """Test process_device with minimal input."""
    result = process_device({"mac": "AA-BB-CC-DD-EE-FF"})
    assert result["mac"] == "AA-BB-CC-DD-EE-FF"
    assert result["name"] == "Unknown Device"
    assert result["model"] == "Unknown"
    assert result["type"] == "unknown"
    assert result["client_num"] == 0
    assert result["need_upgrade"] is False
