"""Client helpers for Omada Open API integration."""

from __future__ import annotations

from typing import Any


def normalize_client_mac(mac: str) -> str:
    """Normalize client MAC for registry comparisons."""
    return mac.replace(":", "-").upper()


def process_client(client: dict[str, Any]) -> dict[str, Any]:
    """Process and normalize client data.

    Args:
        client: Raw client data from API

    Returns:
        Processed client dictionary with normalized fields

    """
    return {
        # Identity
        "mac": client.get("mac"),
        "name": client.get("name") or client.get("hostName") or "Unknown",
        "host_name": client.get("hostName"),
        "ip": client.get("ip"),
        "ipv6_list": client.get("ipv6List", []),
        # Device info
        "vendor": client.get("vendor"),
        "device_type": client.get("deviceType"),
        "device_category": client.get("deviceCategory"),
        "os_name": client.get("osName"),
        "model": client.get("model"),
        # Connection info
        "active": client.get("active", False),
        "wireless": client.get("wireless", False),
        "connect_dev_type": client.get("connectDevType"),
        "ssid": client.get("ssid"),
        "signal_level": client.get("signalLevel"),
        "signal_rank": client.get("signalRank"),
        "rssi": client.get("rssi"),
        # AP connection (wireless)
        "ap_name": client.get("apName"),
        "ap_mac": client.get("apMac"),
        "radio_id": client.get("radioId"),
        "channel": client.get("channel"),
        # Switch connection (wired)
        "switch_name": client.get("switchName"),
        "switch_mac": client.get("switchMac"),
        "port": client.get("port"),
        "port_name": client.get("portName"),
        # Gateway connection
        "gateway_name": client.get("gatewayName"),
        "gateway_mac": client.get("gatewayMac"),
        # Network
        "network_name": client.get("networkName"),
        "vid": client.get("vid"),
        # Traffic
        "activity": client.get("activity"),
        "upload_activity": client.get("uploadActivity"),
        "traffic_down": client.get("trafficDown"),
        "traffic_up": client.get("trafficUp"),
        # Status
        "uptime": client.get("uptime"),
        "last_seen": client.get("lastSeen"),
        "blocked": client.get("blocked", False),
        "guest": client.get("guest", False),
        "auth_status": client.get("authStatus"),
    }
