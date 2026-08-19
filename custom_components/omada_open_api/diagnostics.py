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
    from homeassistant.core import HomeAssistant

    from .types import OmadaConfigEntry, OmadaRuntimeData

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
    hass: HomeAssistant, entry: OmadaConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    rd: OmadaRuntimeData | None = getattr(entry, "runtime_data", None)

    # Gather coordinator data summaries.
    coordinators_summary: dict[str, Any] = {}
    if rd is not None:
        for site_id, coordinator in rd.coordinators.items():
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
    if rd is not None:
        for coordinator in rd.client_coordinators:  # type: ignore[assignment]
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
    if rd is not None:
        for coordinator in rd.app_traffic_coordinators:  # type: ignore[assignment]
            data = coordinator.data or {}
            app_coordinators_summary.append(
                {
                    "site_name": getattr(coordinator, "site_name", "unknown"),
                    "last_update_success": coordinator.last_update_success,
                    "tracked_clients": len(data),
                }
            )

    device_stats_summary: list[dict[str, Any]] = []
    if rd is not None:
        for coordinator in rd.device_stats_coordinators:  # type: ignore[assignment]
            data = coordinator.data or {}
            device_stats_summary.append(
                {
                    "site_name": getattr(coordinator, "site_name", "unknown"),
                    "last_update_success": coordinator.last_update_success,
                    "tracked_devices": len(data),
                }
            )

    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "entry_options": dict(entry.options),
        "has_write_access": rd.has_write_access if rd is not None else False,
        "site_coordinators": coordinators_summary,
        "client_coordinators": client_coordinators_summary,
        "app_traffic_coordinators": app_coordinators_summary,
        "device_stats_coordinators": device_stats_summary,
        "site_devices": {
            site_id: {
                "name": getattr(dev_entry, "name", "unknown"),
                "model": getattr(dev_entry, "model", "unknown"),
            }
            for site_id, dev_entry in (
                rd.site_devices.items() if rd is not None else {}
            )
        },
    }


def _count_device_types(devices: dict[str, dict[str, Any]]) -> dict[str, int]:
    """Count devices by type."""
    counts: dict[str, int] = {}
    for device in devices.values():
        device_type = device.get("type", "unknown")
        counts[device_type] = counts.get(device_type, 0) + 1
    return counts
