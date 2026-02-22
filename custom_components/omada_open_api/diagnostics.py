"""Diagnostics support for the Omada Open API integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN_EXPIRES_AT,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

TO_REDACT = [
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_TOKEN_EXPIRES_AT,
]

# Redact sensitive fields in device/client data.
TO_REDACT_DATA = [
    "mac",
    "ip",
    "ipv6",
    "clientMac",
    "gatewayMac",
]


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime_data: dict[str, Any] = getattr(entry, "runtime_data", {}) or {}

    # Gather coordinator data summaries.
    coordinators_summary: dict[str, Any] = {}
    coordinators = runtime_data.get("coordinators", {})
    for site_id, coordinator in coordinators.items():
        data = coordinator.data or {}
        devices = data.get("devices", {})
        poe_ports = data.get("poe_ports", {})
        ssids = data.get("ssids", [])
        coordinators_summary[site_id] = {
            "site_name": getattr(coordinator, "site_name", "unknown"),
            "last_update_success": coordinator.last_update_success,
            "device_count": len(devices),
            "device_types": _count_device_types(devices),
            "poe_port_count": len(poe_ports),
            "ssid_count": len(ssids),
        }

    client_coordinators_summary: list[dict[str, Any]] = []
    client_coordinators: list[Any] = runtime_data.get("client_coordinators", [])
    for coordinator in client_coordinators:
        data = coordinator.data or {}
        client_coordinators_summary.append(
            {
                "site_name": getattr(coordinator, "site_name", "unknown"),
                "last_update_success": coordinator.last_update_success,
                "client_count": len(data),
                "active_clients": sum(
                    1 for c in data.values() if c.get("active", False)
                ),
                "wireless_clients": sum(
                    1 for c in data.values() if c.get("wireless", False)
                ),
            }
        )

    app_coordinators_summary: list[dict[str, Any]] = []
    app_coordinators: list[Any] = runtime_data.get("app_traffic_coordinators", [])
    for coordinator in app_coordinators:
        data = coordinator.data or {}
        app_coordinators_summary.append(
            {
                "site_name": getattr(coordinator, "site_name", "unknown"),
                "last_update_success": coordinator.last_update_success,
                "tracked_clients": len(data),
            }
        )

    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "entry_options": dict(entry.options),
        "has_write_access": runtime_data.get("has_write_access", False),
        "site_coordinators": coordinators_summary,
        "client_coordinators": client_coordinators_summary,
        "app_traffic_coordinators": app_coordinators_summary,
        "site_devices": {
            site_id: {
                "name": getattr(dev_entry, "name", "unknown"),
                "model": getattr(dev_entry, "model", "unknown"),
            }
            for site_id, dev_entry in runtime_data.get("site_devices", {}).items()
        },
    }


def _count_device_types(devices: dict[str, dict[str, Any]]) -> dict[str, int]:
    """Count devices by type."""
    counts: dict[str, int] = {}
    for device in devices.values():
        device_type = device.get("type", "unknown")
        counts[device_type] = counts.get(device_type, 0) + 1
    return counts
