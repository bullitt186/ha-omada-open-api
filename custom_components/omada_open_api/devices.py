"""Device helpers for Omada Open API integration."""

from __future__ import annotations

import logging
import re
from typing import Any


def normalize_site_id(site_id: str) -> str:
    """Normalize site IDs for registry comparisons."""
    return site_id.upper()


_LOGGER = logging.getLogger(__name__)


def parse_uptime(uptime_str: str | int | None) -> int | None:
    """Parse uptime string to seconds.

    Args:
        uptime_str: Uptime as string (e.g., "4day(s) 17h 26m 57s") or int (seconds)

    Returns:
        Uptime in seconds, or None if parsing fails

    """
    if uptime_str is None:
        return None

    # If already an integer, return it.
    if isinstance(uptime_str, int):
        return uptime_str

    # Parse formatted string like "4day(s) 17h 26m 57s".
    try:
        total_seconds = 0
        # Extract days.
        days_match = re.search(r"(\d+)day", str(uptime_str))
        if days_match:
            total_seconds += int(days_match.group(1)) * 86400

        # Extract hours.
        hours_match = re.search(r"(\d+)h", str(uptime_str))
        if hours_match:
            total_seconds += int(hours_match.group(1)) * 3600

        # Extract minutes.
        minutes_match = re.search(r"(\d+)m", str(uptime_str))
        if minutes_match:
            total_seconds += int(minutes_match.group(1)) * 60

        # Extract seconds.
        seconds_match = re.search(r"(\d+)s", str(uptime_str))
        if seconds_match:
            total_seconds += int(seconds_match.group(1))

        return total_seconds if total_seconds > 0 else None  # noqa: TRY300
    except (ValueError, AttributeError) as err:
        _LOGGER.warning("Failed to parse uptime '%s': %s", uptime_str, err)
        return None


def format_link_speed(speed: int | None) -> str | None:
    """Format link speed enum to readable string.

    0: Auto, 1: 10M, 2: 100M, 3: 1000M (1G), 4: 2500M (2.5G),
    5: 10G, 6: 5G, 7: 25G, 8: 100G
    """
    if speed is None:
        return None

    speed_map = {
        0: "Auto",
        1: "10 Mbps",
        2: "100 Mbps",
        3: "1 Gbps",
        4: "2.5 Gbps",
        5: "10 Gbps",
        6: "5 Gbps",
        7: "25 Gbps",
        8: "100 Gbps",
    }
    return speed_map.get(speed, f"Unknown ({speed})")


def get_device_sort_key(
    device_data: dict[str, Any], device_mac: str
) -> tuple[int, str]:
    """Get sort key for device ordering."""
    device_type = device_data.get("type", "").lower()

    # Priority order: gateway(0), switch(1), others(2).
    if "gateway" in device_type:
        return (0, device_mac)
    if "switch" in device_type:
        return (1, device_mac)
    return (2, device_mac)


# Mapping of detailStatus codes to human-readable strings.
DETAIL_STATUS_MAP: dict[int, str] = {
    0: "Disconnected",
    1: "Disconnected (Migrating)",
    10: "Provisioning",
    11: "Configuring",
    12: "Upgrading",
    13: "Rebooting",
    14: "Connected",
    15: "Connected (Wireless)",
    16: "Connected (Migrating)",
    17: "Connected (Wireless, Migrating)",
    20: "Pending",
    21: "Pending (Wireless)",
    22: "Adopting",
    23: "Adopting (Wireless)",
    24: "Adopt Failed",
    25: "Adopt Failed (Wireless)",
    26: "Managed By Others",
    27: "Managed By Others (Wireless)",
    30: "Heartbeat Missed",
    31: "Heartbeat Missed (Wireless)",
    32: "Heartbeat Missed (Migrating)",
    33: "Heartbeat Missed (Wireless, Migrating)",
    40: "Isolated",
    41: "Isolated (Migrating)",
    50: "Slice Configuring",
}


def format_detail_status(status_code: int | None) -> str | None:
    """Format detailStatus numeric code to human-readable string."""
    if status_code is None:
        return None
    return DETAIL_STATUS_MAP.get(status_code, f"Unknown ({status_code})")


def process_device(device: dict[str, Any]) -> dict[str, Any]:
    """Process raw device data into a normalized format.

    Args:
        device: Raw device data from API

    Returns:
        Processed device data

    """
    return {
        # Identification
        "mac": device.get("mac"),
        "name": device.get("name", "Unknown Device"),
        "model": device.get("model", "Unknown"),
        "model_name": device.get("modelName"),
        "model_version": device.get("modelVersion"),
        "type": device.get("type", "unknown"),
        "subtype": device.get("subtype"),
        "device_series_type": device.get("deviceSeriesType"),
        "sn": device.get("sn"),
        # Status
        "status": device.get("status"),
        "status_category": device.get("statusCategory"),
        "detail_status": device.get("detailStatus"),
        "need_upgrade": device.get("needUpgrade", False),
        "last_seen": device.get("lastSeen"),
        # Network
        "ip": device.get("ip"),
        "ipv6": device.get("ipv6", []),
        "uptime": parse_uptime(device.get("uptime")),
        # Hardware info
        "cpu_util": device.get("cpuUtil"),
        "mem_util": device.get("memUtil"),
        "firmware_version": device.get("firmwareVersion"),
        "compatible": device.get("compatible"),
        "active": device.get("active"),
        # Client info
        "client_num": device.get("clientNum", 0),
        # Uplink info
        "uplink_device_mac": device.get("uplinkDeviceMac"),
        "uplink_device_name": device.get("uplinkDeviceName"),
        "uplink_device_port": device.get("uplinkDevicePort"),
        "link_speed": device.get("linkSpeed"),
        "duplex": device.get("duplex"),
        # Tags and organization
        "tag_name": device.get("tagName"),
        "license_status": device.get("licenseStatus"),
        "in_white_list": device.get("inWhiteList"),
        "switch_consistent": device.get("switchConsistent"),
        # LED
        "led_setting": device.get("ledSetting"),
        # Location (if available)
        "site": device.get("site"),
    }
