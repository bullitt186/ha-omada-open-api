"""Sensor platform for Omada Open API integration."""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfDataRate,
    UnitOfInformation,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import (  # type: ignore[attr-defined]
    DeviceInfo,
    EntityCategory,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ENABLE_DEVICE_BANDWIDTH_SENSORS,
    CONF_ENABLE_DEVICE_DIAGNOSTIC_SENSORS,
    CONF_ENABLE_THREAT_HEATMAP_SENSORS,
    DOMAIN,
    ICON_CLIENTS,
    ICON_CPU,
    ICON_DEVICE_TYPE,
    ICON_DOWNLOAD,
    ICON_IP,
    ICON_LINK,
    ICON_MEMORY,
    ICON_POE,
    ICON_SIGNAL,
    ICON_STATUS,
    ICON_TAG,
    ICON_TEMPERATURE,
    ICON_THREAT_HEATMAP,
    ICON_UPLOAD,
    ICON_UPTIME,
    WAN_SPEED_MAP,
)
from .coordinator import (
    OmadaAppTrafficCoordinator,
    OmadaClientCoordinator,
    OmadaDeviceStatsCoordinator,
    OmadaSiteCoordinator,
    OmadaThreatHeatmapCoordinator,
)
from .devices import (
    build_client_device_info,
    build_infra_device_info,
    format_detail_status,
    format_link_speed,
    get_device_sort_key,
)
from .entity import OmadaEntity

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)

# Sensor keys that belong to the "diagnostic" toggle category.
_DEVICE_DIAGNOSTIC_SENSOR_KEYS: frozenset[str] = frozenset(
    {
        "uptime",
        "cpu_util",
        "mem_util",
        "detail_status",
        "device_ip",
        "public_ip",
        "temperature",
        "ipv6",
        "tag",
        "uplink_device",
        "uplink_port",
        "link_speed",
        "device_type",
    }
)

# Uptime sensor anti-spam: treat a drop in reported uptime >= this value as a reboot.
_UPTIME_REBOOT_THRESHOLD_SECONDS: int = 120
# Uptime sensor anti-spam: minimum change in computed boot timestamp to publish a new state.
_UPTIME_MIN_DELTA_SECONDS: int = 60

# Human-readable labels for device type abbreviations from the API.
DEVICE_TYPE_LABELS: dict[str, str] = {
    "ap": "Access Point",
    "gateway": "Gateway",
    "switch": "Switch",
    "olt": "OLT",
}

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback
    from homeassistant.helpers.typing import StateType

    from .types import OmadaConfigEntry


def _auto_scale_bytes(
    bytes_value: float | None,
) -> tuple[float | None, str | None]:
    """Auto-scale bytes to appropriate unit (B, KB, MB, GB, TB).

    Returns tuple of (scaled_value, unit).
    """
    if bytes_value is None:
        return None, None

    # Convert to float for calculations
    value = float(bytes_value)

    # Define thresholds and units (using decimal: 1 KB = 1000 B)
    if value >= 1_000_000_000_000:  # >= 1 TB
        return value / 1_000_000_000_000, UnitOfInformation.TERABYTES
    if value >= 1_000_000_000:  # >= 1 GB
        return value / 1_000_000_000, UnitOfInformation.GIGABYTES
    if value >= 1_000_000:  # >= 1 MB
        return value / 1_000_000, UnitOfInformation.MEGABYTES
    if value >= 1_000:  # >= 1 KB
        return value / 1_000, UnitOfInformation.KILOBYTES

    return value, UnitOfInformation.BYTES


def _ceil_to_30s(ts: dt.datetime) -> dt.datetime:
    """Round a timestamp up to the next 30-second boundary (ceiling).

    Snapping the computed boot time to a 30-second ceiling prevents the
    "minute flip-flop" where small timing variations cause the displayed
    timestamp to oscillate (e.g. "09:22" <-> "09:23").
    """
    remainder = ts.second % 30
    if remainder == 0:
        return ts
    return ts + dt.timedelta(seconds=30 - remainder)


@dataclass(frozen=True, kw_only=True)
class OmadaSensorEntityDescription(SensorEntityDescription):
    """Describes Omada sensor entity."""

    value_fn: Callable[[dict[str, Any]], StateType]
    available_fn: Callable[[dict[str, Any]], bool] = lambda device: True
    applicable_types: tuple[str, ...] | None = None
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None
    applicable_fn: Callable[[dict[str, Any]], bool] | None = None


DEVICE_SENSORS: tuple[OmadaSensorEntityDescription, ...] = (
    OmadaSensorEntityDescription(
        key="client_num",
        translation_key="client_num",
        name="Connected clients",
        icon=ICON_CLIENTS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: len(device.get("connected_clients", [])),
        attrs_fn=lambda device: {
            "clients": [
                {"name": c["name"], "mac": c["mac"], "ip": c["ip"]}
                for c in device.get("connected_clients", [])
            ]
        },
    ),
    OmadaSensorEntityDescription(
        key="wired_clients",
        translation_key="wired_clients",
        name="Wired clients",
        icon=ICON_CLIENTS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: len(
            [c for c in device.get("connected_clients", []) if not c.get("wireless")]
        ),
        attrs_fn=lambda device: {
            "clients": [
                {"name": c["name"], "mac": c["mac"], "ip": c["ip"]}
                for c in device.get("connected_clients", [])
                if not c.get("wireless")
            ]
        },
        applicable_fn=lambda d: d.get("has_wired_ports", False),
    ),
    OmadaSensorEntityDescription(
        key="wireless_clients",
        translation_key="wireless_clients",
        name="Wireless clients",
        icon=ICON_CLIENTS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: len(
            [c for c in device.get("connected_clients", []) if c.get("wireless")]
        ),
        attrs_fn=lambda device: {
            "clients": [
                {"name": c["name"], "mac": c["mac"], "ip": c["ip"]}
                for c in device.get("connected_clients", [])
                if c.get("wireless")
            ]
        },
        applicable_fn=lambda d: d.get("has_wireless_radio", False),
    ),
    OmadaSensorEntityDescription(
        key="guest_clients",
        translation_key="guest_clients",
        name="Guest clients",
        icon=ICON_CLIENTS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: len(
            [c for c in device.get("connected_clients", []) if c.get("guest")]
        ),
        attrs_fn=lambda device: {
            "clients": [
                {"name": c["name"], "mac": c["mac"], "ip": c["ip"]}
                for c in device.get("connected_clients", [])
                if c.get("guest")
            ]
        },
    ),
    OmadaSensorEntityDescription(
        key="uptime",
        translation_key="uptime",
        name="Uptime",
        icon=ICON_UPTIME,
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda device: (  # type: ignore[arg-type]
            (  # type: ignore[return-value]
                dt_util.utcnow().replace(microsecond=0)
                - dt.timedelta(seconds=device["uptime"])
            )
            if device.get("uptime") is not None
            else None
        ),
        available_fn=lambda device: device.get("uptime") is not None,
    ),
    OmadaSensorEntityDescription(
        key="cpu_util",
        translation_key="cpu_util",
        name="CPU utilization",
        icon=ICON_CPU,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda device: device.get("cpu_util"),
        available_fn=lambda device: device.get("cpu_util") is not None,
    ),
    OmadaSensorEntityDescription(
        key="mem_util",
        translation_key="mem_util",
        name="Memory utilization",
        icon=ICON_MEMORY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda device: device.get("mem_util"),
        available_fn=lambda device: device.get("mem_util") is not None,
    ),
    OmadaSensorEntityDescription(
        key="device_type",
        translation_key="device_type",
        name="Device type",
        icon=ICON_DEVICE_TYPE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: DEVICE_TYPE_LABELS.get(
            device.get("type", ""), device.get("type")
        ),
        available_fn=lambda device: device.get("type") is not None,
    ),
    OmadaSensorEntityDescription(
        key="tag",
        translation_key="tag",
        name="Tag",
        icon=ICON_TAG,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.get("tag_name"),
        available_fn=lambda device: device.get("tag_name") is not None,
    ),
    OmadaSensorEntityDescription(
        key="uplink_device",
        translation_key="uplink_device",
        name="Uplink device",
        icon=ICON_LINK,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.get("uplink_device_name"),
        available_fn=lambda device: device.get("uplink_device_name") is not None,
        applicable_types=("ap", "switch"),
    ),
    OmadaSensorEntityDescription(
        key="uplink_port",
        translation_key="uplink_port",
        name="Uplink port",
        icon=ICON_LINK,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.get("uplink_device_port"),
        available_fn=lambda device: device.get("uplink_device_port") is not None,
        applicable_types=("ap", "switch"),
    ),
    OmadaSensorEntityDescription(
        key="link_speed",
        translation_key="link_speed",
        name="Link speed",
        icon=ICON_LINK,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: format_link_speed(device.get("link_speed")),
        available_fn=lambda device: device.get("link_speed") is not None,
        applicable_types=("ap", "switch"),
    ),
    OmadaSensorEntityDescription(
        key="device_ip",
        translation_key="device_ip",
        name="IP Address",
        icon=ICON_IP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.get("ip"),
        available_fn=lambda device: bool(device.get("ip")),
    ),
    OmadaSensorEntityDescription(
        key="ipv6",
        translation_key="ipv6",
        name="IPv6 addresses",
        icon="mdi:ip-network",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda device: (
            ", ".join(device.get("ipv6", [])) if device.get("ipv6") else None
        ),
        available_fn=lambda device: bool(device.get("ipv6")),
    ),
    OmadaSensorEntityDescription(
        key="detail_status",
        translation_key="detail_status",
        name="Detail status",
        icon=ICON_STATUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda device: format_detail_status(device.get("detail_status")),
        available_fn=lambda device: device.get("detail_status") is not None,
    ),
    OmadaSensorEntityDescription(
        key="temperature",
        translation_key="temperature",
        name="Temperature",
        icon=ICON_TEMPERATURE,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.get("temperature"),
        available_fn=lambda device: device.get("temperature") is not None,
        applicable_types=("gateway",),
    ),
    OmadaSensorEntityDescription(
        key="public_ip",
        translation_key="public_ip",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.get("public_ip"),
        available_fn=lambda device: bool(device.get("public_ip")),
        applicable_types=("gateway",),
    ),
    OmadaSensorEntityDescription(
        key="rx_activity",
        translation_key="rx_activity",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABYTES_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        # Rates are computed from AP radio traffic counters — AP devices only.
        applicable_types=("ap",),
        value_fn=lambda d: d.get("rx_rate_mbps"),
        available_fn=lambda d: d.get("rx_rate_mbps") is not None,
    ),
    OmadaSensorEntityDescription(
        key="tx_activity",
        translation_key="tx_activity",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABYTES_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        applicable_types=("ap",),
        value_fn=lambda d: d.get("tx_rate_mbps"),
        available_fn=lambda d: d.get("tx_rate_mbps") is not None,
    ),
)

# Radio ID to band mapping for filtering clients by radio.
_RADIO_BAND_MAP: dict[str, int] = {
    "clients_2g": 0,
    "clients_5g": 1,
    "clients_5g2": 2,
    "clients_6g": 3,
}


def _band_clients_attrs(
    radio_id: int,
) -> Callable[[dict[str, Any]], dict[str, Any] | None]:
    """Return attrs_fn that filters connected wireless clients by radio ID."""

    def _attrs(device: dict[str, Any]) -> dict[str, Any] | None:
        return {
            "clients": [
                {"name": c["name"], "mac": c["mac"], "ip": c["ip"]}
                for c in device.get("connected_clients", [])
                if c.get("wireless") and c.get("radio_id") == radio_id
            ]
        }

    return _attrs


# Per-band client count sensors (AP-only, populated by coordinator)
AP_BAND_CLIENT_SENSORS: tuple[OmadaSensorEntityDescription, ...] = (
    OmadaSensorEntityDescription(
        key="clients_2g",
        translation_key="clients_2g",
        name="Clients 2.4 GHz",
        icon=ICON_CLIENTS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.get("client_num_2g"),
        available_fn=lambda device: device.get("client_num_2g") is not None,
        attrs_fn=_band_clients_attrs(0),
    ),
    OmadaSensorEntityDescription(
        key="clients_5g",
        translation_key="clients_5g",
        name="Clients 5 GHz-1",
        icon=ICON_CLIENTS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.get("client_num_5g"),
        available_fn=lambda device: device.get("client_num_5g") is not None,
        attrs_fn=_band_clients_attrs(1),
    ),
    OmadaSensorEntityDescription(
        key="clients_5g2",
        translation_key="clients_5g2",
        name="Clients 5 GHz-2",
        icon=ICON_CLIENTS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.get("client_num_5g2"),
        available_fn=lambda device: device.get("client_num_5g2") is not None,
        attrs_fn=_band_clients_attrs(2),
    ),
    OmadaSensorEntityDescription(
        key="clients_6g",
        translation_key="clients_6g",
        name="Clients 6 GHz",
        icon=ICON_CLIENTS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.get("client_num_6g"),
        available_fn=lambda device: device.get("client_num_6g") is not None,
        attrs_fn=_band_clients_attrs(3),
    ),
)

# Per-band radio utilization sensors (AP-only, populated by coordinator every 5 min)
AP_BAND_RADIO_UTIL_SENSORS: tuple[OmadaSensorEntityDescription, ...] = (
    OmadaSensorEntityDescription(
        key="radio_tx_util_2g",
        translation_key="radio_tx_util_2g",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("radio_tx_util_2g"),
        available_fn=lambda d: d.get("radio_tx_util_2g") is not None,
    ),
    OmadaSensorEntityDescription(
        key="radio_rx_util_2g",
        translation_key="radio_rx_util_2g",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("radio_rx_util_2g"),
        available_fn=lambda d: d.get("radio_rx_util_2g") is not None,
    ),
    OmadaSensorEntityDescription(
        key="radio_inter_util_2g",
        translation_key="radio_inter_util_2g",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("radio_inter_util_2g"),
        available_fn=lambda d: d.get("radio_inter_util_2g") is not None,
    ),
    OmadaSensorEntityDescription(
        key="radio_busy_util_2g",
        translation_key="radio_busy_util_2g",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("radio_busy_util_2g"),
        available_fn=lambda d: d.get("radio_busy_util_2g") is not None,
    ),
    OmadaSensorEntityDescription(
        key="radio_tx_util_5g",
        translation_key="radio_tx_util_5g",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("radio_tx_util_5g"),
        available_fn=lambda d: d.get("radio_tx_util_5g") is not None,
    ),
    OmadaSensorEntityDescription(
        key="radio_rx_util_5g",
        translation_key="radio_rx_util_5g",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("radio_rx_util_5g"),
        available_fn=lambda d: d.get("radio_rx_util_5g") is not None,
    ),
    OmadaSensorEntityDescription(
        key="radio_inter_util_5g",
        translation_key="radio_inter_util_5g",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("radio_inter_util_5g"),
        available_fn=lambda d: d.get("radio_inter_util_5g") is not None,
    ),
    OmadaSensorEntityDescription(
        key="radio_busy_util_5g",
        translation_key="radio_busy_util_5g",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("radio_busy_util_5g"),
        available_fn=lambda d: d.get("radio_busy_util_5g") is not None,
    ),
    OmadaSensorEntityDescription(
        key="radio_tx_util_5g2",
        translation_key="radio_tx_util_5g2",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("radio_tx_util_5g2"),
        available_fn=lambda d: d.get("radio_tx_util_5g2") is not None,
    ),
    OmadaSensorEntityDescription(
        key="radio_rx_util_5g2",
        translation_key="radio_rx_util_5g2",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("radio_rx_util_5g2"),
        available_fn=lambda d: d.get("radio_rx_util_5g2") is not None,
    ),
    OmadaSensorEntityDescription(
        key="radio_inter_util_5g2",
        translation_key="radio_inter_util_5g2",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("radio_inter_util_5g2"),
        available_fn=lambda d: d.get("radio_inter_util_5g2") is not None,
    ),
    OmadaSensorEntityDescription(
        key="radio_busy_util_5g2",
        translation_key="radio_busy_util_5g2",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("radio_busy_util_5g2"),
        available_fn=lambda d: d.get("radio_busy_util_5g2") is not None,
    ),
    OmadaSensorEntityDescription(
        key="radio_tx_util_6g",
        translation_key="radio_tx_util_6g",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("radio_tx_util_6g"),
        available_fn=lambda d: d.get("radio_tx_util_6g") is not None,
    ),
    OmadaSensorEntityDescription(
        key="radio_rx_util_6g",
        translation_key="radio_rx_util_6g",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("radio_rx_util_6g"),
        available_fn=lambda d: d.get("radio_rx_util_6g") is not None,
    ),
    OmadaSensorEntityDescription(
        key="radio_inter_util_6g",
        translation_key="radio_inter_util_6g",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("radio_inter_util_6g"),
        available_fn=lambda d: d.get("radio_inter_util_6g") is not None,
    ),
    OmadaSensorEntityDescription(
        key="radio_busy_util_6g",
        translation_key="radio_busy_util_6g",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("radio_busy_util_6g"),
        available_fn=lambda d: d.get("radio_busy_util_6g") is not None,
    ),
)

# Client sensor descriptions
CLIENT_SENSORS: tuple[OmadaSensorEntityDescription, ...] = (
    OmadaSensorEntityDescription(
        key="connection_status",
        translation_key="connection_status",
        name="Connection Status",
        icon="mdi:network",
        value_fn=lambda client: "Connected" if client.get("active") else "Disconnected",
    ),
    OmadaSensorEntityDescription(
        key="ip_address",
        translation_key="ip_address",
        name="IP Address",
        icon="mdi:ip-network",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda client: client.get("ip"),
    ),
    OmadaSensorEntityDescription(
        key="signal_strength",
        translation_key="signal_strength",
        name="Signal Strength",
        icon="mdi:wifi-strength-4",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda client: client.get("signal_level"),
        available_fn=lambda client: (
            client.get("wireless", False) and client.get("signal_level") is not None
        ),
    ),
    OmadaSensorEntityDescription(
        key="connected_to",
        translation_key="connected_to",
        name="Connected To",
        icon="mdi:access-point",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda client: (
            client.get("ap_name")
            or client.get("switch_name")
            or client.get("gateway_name")
        ),
    ),
    OmadaSensorEntityDescription(
        key="ssid",
        translation_key="ssid",
        name="SSID",
        icon="mdi:wifi",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda client: client.get("ssid"),
        available_fn=lambda client: client.get("wireless", False),
    ),
    OmadaSensorEntityDescription(
        key="downloaded",
        translation_key="downloaded",
        name="Downloaded",
        icon=ICON_DOWNLOAD,
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        suggested_display_precision=1,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda client: (
            round(client["traffic_down"] / 1_000_000, 1)
            if client.get("traffic_down") is not None
            else None
        ),
        available_fn=lambda client: client.get("traffic_down") is not None,
    ),
    OmadaSensorEntityDescription(
        key="uploaded",
        translation_key="uploaded",
        name="Uploaded",
        icon=ICON_UPLOAD,
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        suggested_display_precision=1,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda client: (
            round(client["traffic_up"] / 1_000_000, 1)
            if client.get("traffic_up") is not None
            else None
        ),
        available_fn=lambda client: client.get("traffic_up") is not None,
    ),
    OmadaSensorEntityDescription(
        key="rx_activity",
        translation_key="rx_activity",
        name="RX Activity",
        icon=ICON_DOWNLOAD,
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement="MB/s",
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda client: round((client.get("activity") or 0) / 1_000_000, 2),
        available_fn=lambda client: client.get("active", False),
    ),
    OmadaSensorEntityDescription(
        key="tx_activity",
        translation_key="tx_activity",
        name="TX Activity",
        icon=ICON_UPLOAD,
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement="MB/s",
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda client: round(
            (client.get("upload_activity") or 0) / 1_000_000, 2
        ),
        available_fn=lambda client: client.get("active", False),
    ),
    OmadaSensorEntityDescription(
        key="rssi",
        translation_key="rssi",
        name="RSSI",
        icon=ICON_SIGNAL,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement="dBm",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda client: client.get("rssi"),
        available_fn=lambda client: (
            client.get("wireless", False) and client.get("rssi") is not None
        ),
    ),
    OmadaSensorEntityDescription(
        key="snr",
        translation_key="snr",
        name="SNR",
        icon=ICON_SIGNAL,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement="dB",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda client: client.get("snr"),
        available_fn=lambda client: (
            client.get("wireless", False) and client.get("snr") is not None
        ),
    ),
    OmadaSensorEntityDescription(
        key="client_uptime",
        translation_key="client_uptime",
        name="Uptime",
        icon=ICON_UPTIME,
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda client: (  # type: ignore[arg-type]
            (  # type: ignore[return-value]
                dt_util.utcnow().replace(microsecond=0)
                - dt.timedelta(seconds=client["uptime"])
            )
            if client.get("uptime") is not None
            else None
        ),
        available_fn=lambda client: client.get("uptime") is not None,
    ),
)


# PoE budget sensor descriptions (per-switch totals)
POE_BUDGET_SENSORS: tuple[OmadaSensorEntityDescription, ...] = (
    OmadaSensorEntityDescription(
        key="poe_power_budget",
        translation_key="poe_power_budget",
        name="PoE power budget",
        icon=ICON_POE,
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("total_power"),
        available_fn=lambda data: data.get("total_power") is not None,
    ),
    OmadaSensorEntityDescription(
        key="poe_power_used",
        translation_key="poe_power_used",
        name="PoE power used",
        icon=ICON_POE,
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("total_power_used"),
        available_fn=lambda data: data.get("total_power_used") is not None,
    ),
    OmadaSensorEntityDescription(
        key="poe_power_remaining_percent",
        translation_key="poe_power_remaining_percent",
        name="PoE power remaining",
        icon=ICON_POE,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: (
            round(100.0 - data["total_percent_used"], 1)
            if data.get("total_percent_used") is not None
            else None
        ),
        available_fn=lambda data: data.get("total_percent_used") is not None,
    ),
)


# WAN port sensor descriptions (per-port, using translation_placeholders)
WAN_PORT_SENSORS: tuple[OmadaSensorEntityDescription, ...] = (
    OmadaSensorEntityDescription(
        key="wan_download_rate",
        translation_key="wan_download_rate",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.KILOBYTES_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda port: port.get("rxRate"),
        available_fn=lambda port: port.get("rxRate") is not None,
    ),
    OmadaSensorEntityDescription(
        key="wan_upload_rate",
        translation_key="wan_upload_rate",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.KILOBYTES_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda port: port.get("txRate"),
        available_fn=lambda port: port.get("txRate") is not None,
    ),
    OmadaSensorEntityDescription(
        key="wan_download_total",
        translation_key="wan_download_total",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda port: port.get("rx", 0) / 1_000_000,
        available_fn=lambda port: port.get("rx") is not None,
    ),
    OmadaSensorEntityDescription(
        key="wan_upload_total",
        translation_key="wan_upload_total",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda port: port.get("tx", 0) / 1_000_000,
        available_fn=lambda port: port.get("tx") is not None,
    ),
    OmadaSensorEntityDescription(
        key="wan_latency",
        translation_key="wan_latency",
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda port: port.get("latency"),
        available_fn=lambda port: (
            port.get("latency") is not None and port.get("status") == 1
        ),
    ),
    OmadaSensorEntityDescription(
        key="wan_packet_loss",
        translation_key="wan_packet_loss",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda port: port.get("loss"),
        available_fn=lambda port: (
            port.get("loss") is not None and port.get("status") == 1
        ),
    ),
    OmadaSensorEntityDescription(
        key="wan_ip_address",
        translation_key="wan_ip_address",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda port: port.get("ip"),
        available_fn=lambda port: bool(port.get("ip")),
    ),
    OmadaSensorEntityDescription(
        key="wan_link_speed",
        translation_key="wan_link_speed",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="Mbps",
        value_fn=lambda port: WAN_SPEED_MAP.get(port.get("speed", 0)),
        available_fn=lambda port: port.get("speed") is not None,
    ),
    OmadaSensorEntityDescription(
        key="wan_ipv6_address",
        translation_key="wan_ipv6_address",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda port: port.get("wanPortIpv6Config", {}).get("addr"),
        available_fn=lambda port: (
            bool(port.get("wanPortIpv6Config", {}).get("addr"))
            and port.get("wanPortIpv6Config", {}).get("enable") == 1
        ),
    ),
)


# WAN speed test sensor descriptions (one set per gateway)
WAN_SPEED_SENSORS: tuple[OmadaSensorEntityDescription, ...] = (
    OmadaSensorEntityDescription(
        key="wan_speed_download",
        translation_key="wan_speed_download",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda st: st.get("downloadSpeed"),
        available_fn=lambda st: st.get("downloadSpeed") is not None,
    ),
    OmadaSensorEntityDescription(
        key="wan_speed_upload",
        translation_key="wan_speed_upload",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda st: st.get("uploadSpeed"),
        available_fn=lambda st: st.get("uploadSpeed") is not None,
    ),
    OmadaSensorEntityDescription(
        key="wan_speed_latency",
        translation_key="wan_speed_latency",
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda st: st.get("latency"),
        available_fn=lambda st: st.get("latency") is not None,
    ),
    OmadaSensorEntityDescription(
        key="wan_speed_last_test",
        translation_key="wan_speed_last_test",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda st: st.get("testTime"),
        available_fn=lambda st: st.get("testTime") is not None,
    ),
)

# Device daily traffic sensor descriptions
DEVICE_TRAFFIC_SENSORS: tuple[OmadaSensorEntityDescription, ...] = (
    OmadaSensorEntityDescription(
        key="daily_download",
        translation_key="daily_download",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda data: data.get("daily_rx", 0) / 1_000_000,
        available_fn=lambda data: data.get("daily_rx") is not None,
    ),
    OmadaSensorEntityDescription(
        key="daily_upload",
        translation_key="daily_upload",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda data: data.get("daily_tx", 0) / 1_000_000,
        available_fn=lambda data: data.get("daily_tx") is not None,
    ),
)


def _build_wan_sensors(
    coordinator: OmadaSiteCoordinator,
    wan_status: dict[str, list[dict[str, Any]]],
    known_wan_port_keys: set[str],
) -> list[SensorEntity]:
    """Create WAN port sensor entities for all new ports.

    Args:
        coordinator: Site coordinator providing WAN data
        wan_status: WAN status dict keyed by gateway MAC
        known_wan_port_keys: Set of already-known WAN port keys (mutated)

    Returns:
        List of new WAN sensor entities

    """
    entities: list[SensorEntity] = []
    for gw_mac, ports in wan_status.items():
        for port_idx, port_data in enumerate(ports):
            port_name = port_data.get("name", f"WAN{port_idx + 1}")
            wan_key = f"{gw_mac}_wan_{port_idx}"
            if wan_key not in known_wan_port_keys:
                known_wan_port_keys.add(wan_key)
                entities.extend(
                    OmadaWanSensor(
                        coordinator=coordinator,
                        description=desc,
                        gateway_mac=gw_mac,
                        port_index=port_idx,
                        port_name=port_name,
                    )
                    for desc in WAN_PORT_SENSORS
                )
    return entities


def _build_wan_speed_sensors(
    coordinator: OmadaSiteCoordinator,
    wan_speed_test: dict[str, Any],
    devices: dict[str, Any],
    known_wan_speed_keys: set[str],
) -> list[SensorEntity]:
    """Create WAN speed test sensor entities for gateway devices.

    Args:
        coordinator: Site coordinator providing WAN data
        wan_speed_test: WAN speed test result dict keyed by gateway MAC
        devices: Device data dict keyed by MAC
        known_wan_speed_keys: Set of already-known WAN speed keys (mutated)

    Returns:
        List of new WAN speed sensor entities

    """
    entities: list[SensorEntity] = []
    if not wan_speed_test:
        return entities
    for gw_mac_key, gw_dev in devices.items():
        if gw_dev.get("type", "").lower() != "gateway":
            continue
        for desc in WAN_SPEED_SENSORS:
            ent_key = f"{gw_mac_key}_{desc.key}"
            if ent_key not in known_wan_speed_keys:
                known_wan_speed_keys.add(ent_key)
                entities.append(
                    OmadaWanSpeedSensor(
                        coordinator=coordinator,
                        description=desc,
                        gateway_mac=gw_mac_key,
                    )
                )
    return entities


# ---------------------------------------------------------------------------
# Site-level aggregation sensors
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class OmadaSiteSensorEntityDescription(SensorEntityDescription):
    """Describes an Omada site-level aggregation sensor."""

    value_fn: Callable[[dict[str, Any]], StateType]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None


def _site_total_clients(data: dict[str, Any]) -> int:
    """Return total active client count for the site."""
    return len(data.get("all_clients", []))


def _site_wired_clients(data: dict[str, Any]) -> int:
    """Return wired client count for the site."""
    return len([c for c in data.get("all_clients", []) if not c.get("wireless")])


def _site_wireless_clients(data: dict[str, Any]) -> int:
    """Return wireless client count for the site."""
    return len([c for c in data.get("all_clients", []) if c.get("wireless")])


def _site_guest_clients(data: dict[str, Any]) -> int:
    """Return guest client count for the site."""
    return len([c for c in data.get("all_clients", []) if c.get("guest")])


def _site_poe_consumption(data: dict[str, Any]) -> float:
    """Return total PoE consumption in watts across all switches."""
    poe_budget = data.get("poe_budget", {})
    return float(
        round(
            sum(float(sw.get("total_power_used", 0.0)) for sw in poe_budget.values()),
            1,
        )
    )


def _client_list_attrs(
    clients: list[dict[str, Any]],
) -> dict[str, Any]:
    """Format a lightweight client list for Jinja2 use."""
    return {
        "clients": [
            {"name": c["name"], "mac": c["mac"], "ip": c["ip"]} for c in clients
        ]
    }


SITE_SENSORS: tuple[OmadaSiteSensorEntityDescription, ...] = (
    OmadaSiteSensorEntityDescription(
        key="site_total_clients",
        translation_key="site_total_clients",
        name="Total clients",
        icon=ICON_CLIENTS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_site_total_clients,
        attrs_fn=lambda data: _client_list_attrs(data.get("all_clients", [])),
    ),
    OmadaSiteSensorEntityDescription(
        key="site_wired_clients",
        translation_key="site_wired_clients",
        name="Wired clients",
        icon=ICON_CLIENTS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_site_wired_clients,
        attrs_fn=lambda data: _client_list_attrs(
            [c for c in data.get("all_clients", []) if not c.get("wireless")]
        ),
    ),
    OmadaSiteSensorEntityDescription(
        key="site_wireless_clients",
        translation_key="site_wireless_clients",
        name="Wireless clients",
        icon=ICON_CLIENTS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_site_wireless_clients,
        attrs_fn=lambda data: _client_list_attrs(
            [c for c in data.get("all_clients", []) if c.get("wireless")]
        ),
    ),
    OmadaSiteSensorEntityDescription(
        key="site_guest_clients",
        translation_key="site_guest_clients",
        name="Guest clients",
        icon=ICON_CLIENTS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_site_guest_clients,
        attrs_fn=lambda data: _client_list_attrs(
            [c for c in data.get("all_clients", []) if c.get("guest")]
        ),
    ),
    OmadaSiteSensorEntityDescription(
        key="site_poe_consumption",
        translation_key="site_poe_consumption",
        name="PoE consumption",
        icon=ICON_POE,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        value_fn=_site_poe_consumption,
    ),
)


def _setup_site_sensors(
    coordinators: dict[str, OmadaSiteCoordinator],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create site-level aggregation sensors for all coordinators."""
    site_entities: list[SensorEntity] = [
        OmadaSiteSensor(coordinator=coord, description=desc)
        for coord in coordinators.values()
        for desc in SITE_SENSORS
    ]
    if site_entities:
        async_add_entities(site_entities)


def _setup_threat_heatmap_sensors(
    coordinators: list[OmadaThreatHeatmapCoordinator],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one threat heatmap sensor per site/window coordinator."""
    entities: list[SensorEntity] = [
        OmadaThreatHeatmapSensor(coordinator=coord) for coord in coordinators
    ]
    if entities:
        async_add_entities(entities)


def _make_device_sensor(
    coordinator: OmadaSiteCoordinator,
    description: OmadaSensorEntityDescription,
    device_mac: str,
) -> OmadaDeviceSensor:
    """Instantiate the appropriate device sensor class for *description*."""
    if description.key == "uptime":
        return OmadaDeviceUptimeSensor(
            coordinator=coordinator,
            description=description,
            device_mac=device_mac,
        )
    return OmadaDeviceSensor(
        coordinator=coordinator,
        description=description,
        device_mac=device_mac,
    )


def _make_client_sensor(
    coordinator: OmadaClientCoordinator,
    description: OmadaSensorEntityDescription,
    client_mac: str,
) -> OmadaClientSensor:
    """Instantiate the appropriate client sensor class for *description*."""
    if description.key == "client_uptime":
        return OmadaClientUptimeSensor(
            coordinator=coordinator,
            description=description,
            client_mac=client_mac,
        )
    return OmadaClientSensor(
        coordinator=coordinator,
        description=description,
        client_mac=client_mac,
    )


def _purge_absent_band_entities(
    hass: HomeAssistant,
    entry: OmadaConfigEntry,
    coordinators: dict[str, OmadaSiteCoordinator],
) -> None:
    """Remove entity registry entries for band sensors whose band is absent on hardware."""
    reg = er.async_get(hass)
    all_band_keys = {desc.key for desc in AP_BAND_CLIENT_SENSORS} | {
        desc.key for desc in AP_BAND_RADIO_UTIL_SENSORS
    }

    present_keys: set[tuple[str, str]] = set()
    for coord in coordinators.values():
        devices = coord.data.get("devices", {}) if coord.data else {}
        for mac, device_data in devices.items():
            if device_data.get("type", "").lower() != "ap":
                continue
            for desc in AP_BAND_CLIENT_SENSORS:
                data_key = desc.key.replace("clients_", "client_num_")
                if data_key in device_data:
                    present_keys.add((mac, desc.key))
            for desc in AP_BAND_RADIO_UTIL_SENSORS:
                if desc.key in device_data:
                    present_keys.add((mac, desc.key))

    for entity_entry in er.async_entries_for_config_entry(reg, entry.entry_id):
        if entity_entry.platform != DOMAIN:
            continue
        parts = entity_entry.unique_id.split("_", 1)
        if len(parts) != 2:
            continue
        mac, key = parts
        if key in all_band_keys and (mac, key) not in present_keys:
            reg.async_remove(entity_entry.entity_id)


_5G_BAND_KEYS: frozenset[str] = frozenset(
    {
        "clients_5g",
        "radio_tx_util_5g",
        "radio_rx_util_5g",
        "radio_inter_util_5g",
        "radio_busy_util_5g",
    }
)


def _migrate_5g_entity_ids(
    hass: HomeAssistant,
    entry: OmadaConfigEntry,
) -> None:
    """Rename legacy _5_ghz_1 entity IDs to _5_ghz after translations dropped the -1."""
    reg = er.async_get(hass)
    for entity_entry in er.async_entries_for_config_entry(reg, entry.entry_id):
        if entity_entry.platform != DOMAIN:
            continue
        parts = entity_entry.unique_id.split("_", 1)
        if len(parts) != 2 or parts[1] not in _5G_BAND_KEYS:
            continue
        old_id = entity_entry.entity_id
        if not old_id.endswith("_5_ghz_1"):
            continue
        new_id = old_id[:-2]  # strip trailing "_1"
        if reg.async_get(new_id) is None:
            reg.async_update_entity(old_id, new_entity_id=new_id)


def _check_ap_band_entities(
    coord: OmadaSiteCoordinator,
    devices: Any,
    known_keys: set[tuple[str, str]],
) -> list[SensorEntity]:
    """Return new per-band entities for APs whose band data just appeared."""
    new_entities: list[SensorEntity] = []
    for mac, device_data in devices.items():
        if device_data.get("type", "").lower() != "ap":
            continue
        for desc in AP_BAND_CLIENT_SENSORS:
            data_key = desc.key.replace("clients_", "client_num_")
            if (mac, desc.key) not in known_keys and data_key in device_data:
                known_keys.add((mac, desc.key))
                new_entities.append(_make_device_sensor(coord, desc, mac))
        for desc in AP_BAND_RADIO_UTIL_SENSORS:
            if (mac, desc.key) not in known_keys and desc.key in device_data:
                known_keys.add((mac, desc.key))
                new_entities.append(_make_device_sensor(coord, desc, mac))
    return new_entities


async def async_setup_entry(  # pylint: disable=too-many-locals,too-many-statements
    hass: HomeAssistant,
    entry: OmadaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Omada sensors from a config entry."""
    rd = entry.runtime_data
    coordinators: dict[str, OmadaSiteCoordinator] = rd.coordinators
    client_coordinators: list[OmadaClientCoordinator] = rd.client_coordinators
    app_traffic_coordinators: list[OmadaAppTrafficCoordinator] = (
        rd.app_traffic_coordinators
    )

    # Entity type toggles — all default True (preserve existing behavior)
    opts = entry.options
    _enable_device_bandwidth = opts.get(CONF_ENABLE_DEVICE_BANDWIDTH_SENSORS, True)
    _enable_device_diagnostic = opts.get(CONF_ENABLE_DEVICE_DIAGNOSTIC_SENSORS, True)
    device_stats_coordinators: list[OmadaDeviceStatsCoordinator] = (
        rd.device_stats_coordinators
    )
    _enable_threat_heatmap = opts.get(CONF_ENABLE_THREAT_HEATMAP_SENSORS, True)

    _setup_site_sensors(coordinators, async_add_entities)
    if _enable_threat_heatmap:
        _setup_threat_heatmap_sensors(
            rd.threat_heatmap_coordinators, async_add_entities
        )
    _migrate_5g_entity_ids(hass, entry)
    _purge_absent_band_entities(hass, entry, coordinators)

    # --- Dynamic infrastructure device sensors ---
    known_device_macs: set[str] = set()
    known_ap_band_entity_keys: set[tuple[str, str]] = set()  # (mac, desc.key)
    known_poe_ports: set[str] = set()
    known_poe_budget_switches: set[str] = set()
    known_wan_port_keys: set[str] = set()
    known_wan_speed_keys: set[str] = set()

    for coordinator in coordinators.values():

        @callback
        def _async_check_new_devices(
            coord: OmadaSiteCoordinator = coordinator,
        ) -> None:
            """Add sensors for newly discovered devices, PoE ports, and budgets."""
            new_entities: list[SensorEntity] = []

            # Device sensors for new infrastructure devices.
            devices = coord.data.get("devices", {}) if coord.data else {}
            new_device_macs = set(devices.keys()) - known_device_macs
            if new_device_macs:
                known_device_macs.update(new_device_macs)

                # Sort new devices by dependency order.
                new_device_list = [(coord, mac) for mac in new_device_macs]
                new_device_list.sort(
                    key=lambda x: get_device_sort_key(
                        x[0].data.get("devices", {}).get(x[1], {}), x[1]
                    )
                )

                for c, mac in new_device_list:
                    device = devices.get(mac, {})
                    device_type = device.get("type", "").lower()
                    new_entities.extend(
                        _make_device_sensor(c, desc, mac)
                        for desc in DEVICE_SENSORS
                        if (
                            desc.applicable_types is None
                            or device_type in desc.applicable_types
                        )
                        and (desc.applicable_fn is None or desc.applicable_fn(device))
                        and (
                            _enable_device_diagnostic
                            or desc.key not in _DEVICE_DIAGNOSTIC_SENSOR_KEYS
                        )
                    )

            # Per-band sensors — run for all APs on every coordinator update.
            new_entities.extend(
                _check_ap_band_entities(coord, devices, known_ap_band_entity_keys)
            )

            # PoE budget sensors for new switches.
            poe_budget = coord.data.get("poe_budget", {})
            new_budget_switches = set(poe_budget.keys()) - known_poe_budget_switches
            if new_budget_switches:
                known_poe_budget_switches.update(new_budget_switches)
                new_entities.extend(
                    OmadaPoeBudgetSensor(
                        coordinator=coord,
                        description=desc,
                        switch_mac=sw_mac,
                    )
                    for sw_mac in new_budget_switches
                    for desc in POE_BUDGET_SENSORS
                )

            # PoE port sensors.
            poe_ports = coord.data.get("poe_ports", {})
            new_poe = set(poe_ports.keys()) - known_poe_ports
            if new_poe:
                known_poe_ports.update(new_poe)
                new_entities.extend(
                    OmadaPoeSensor(coordinator=coord, port_key=pk) for pk in new_poe
                )

            # WAN port sensors for gateway devices.
            wan_status = coord.data.get("wan_status", {})
            new_entities.extend(
                _build_wan_sensors(coord, wan_status, known_wan_port_keys)
            )

            # WAN speed test sensors for gateway devices.
            new_entities.extend(
                _build_wan_speed_sensors(
                    coord,
                    coord.data.get("wan_speed_test", {}),
                    devices,
                    known_wan_speed_keys,
                )
            )

            if new_entities:
                async_add_entities(new_entities)

        _async_check_new_devices()
        entry.async_on_unload(coordinator.async_add_listener(_async_check_new_devices))

    # --- Dynamic client sensors ---
    known_client_macs: set[str] = set()

    for client_coord in client_coordinators:

        @callback
        def _async_check_new_clients(
            coord: OmadaClientCoordinator = client_coord,
        ) -> None:
            """Add sensors for newly discovered clients."""
            new_macs = set(coord.data.keys()) - known_client_macs
            if not new_macs:
                return

            known_client_macs.update(new_macs)

            new_entities: list[SensorEntity] = [
                _make_client_sensor(coord, desc, mac)
                for mac in new_macs
                for desc in CLIENT_SENSORS
            ]
            if new_entities:
                async_add_entities(new_entities)

        _async_check_new_clients()
        entry.async_on_unload(client_coord.async_add_listener(_async_check_new_clients))

    # --- Dynamic app traffic sensors ---
    known_app_traffic_keys: set[str] = set()

    for app_coord in app_traffic_coordinators:

        @callback
        def _async_check_new_app_traffic(
            coord: OmadaAppTrafficCoordinator = app_coord,
        ) -> None:
            """Add sensors for newly discovered client app traffic."""
            new_entities: list[SensorEntity] = []

            for client_mac, client_apps in coord.data.items():
                for app_id, app_data in client_apps.items():
                    for metric_type in ("upload", "download"):
                        key = f"{client_mac}_{app_id}_{metric_type}"
                        if key not in known_app_traffic_keys:
                            known_app_traffic_keys.add(key)
                            new_entities.append(
                                OmadaClientAppTrafficSensor(
                                    coordinator=coord,
                                    client_mac=client_mac,
                                    app_id=app_id,
                                    app_name=app_data.get("app_name", "Unknown"),
                                    metric_type=metric_type,
                                )
                            )

            if new_entities:
                async_add_entities(new_entities)

        _async_check_new_app_traffic()
        entry.async_on_unload(
            app_coord.async_add_listener(_async_check_new_app_traffic)
        )

    # --- Dynamic device daily traffic sensors (skipped when bandwidth toggle is off) ---
    known_traffic_device_macs: set[str] = set()

    if not _enable_device_bandwidth:
        _LOGGER.debug("Device bandwidth sensors disabled via options toggle")

    for stats_coord in device_stats_coordinators if _enable_device_bandwidth else []:

        @callback
        def _async_check_new_traffic_devices(
            coord: OmadaDeviceStatsCoordinator = stats_coord,
        ) -> None:
            """Add daily traffic sensors for newly discovered devices."""
            new_macs = set(coord.data.keys()) - known_traffic_device_macs
            if not new_macs:
                return

            known_traffic_device_macs.update(new_macs)

            new_entities: list[SensorEntity] = [
                OmadaDeviceTrafficSensor(
                    coordinator=coord,
                    description=desc,
                    device_mac=mac,
                )
                for mac in new_macs
                for desc in DEVICE_TRAFFIC_SENSORS
            ]
            if new_entities:
                async_add_entities(new_entities)

        _async_check_new_traffic_devices()
        entry.async_on_unload(
            stats_coord.async_add_listener(_async_check_new_traffic_devices)
        )


class OmadaDeviceSensor(OmadaEntity[OmadaSiteCoordinator], SensorEntity):
    """Representation of an Omada device sensor."""

    entity_description: OmadaSensorEntityDescription

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
        description: OmadaSensorEntityDescription,
        device_mac: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._device_mac = device_mac
        self._attr_unique_id = f"{device_mac}_{description.key}"

        # Set device info
        device_data = coordinator.data.get("devices", {}).get(device_mac, {})

        # Determine device type and via_device
        device_type = device_data.get("type", "").lower()
        uplink_mac = device_data.get("uplink_device_mac")

        # Build device info
        di = build_infra_device_info(
            device_mac, device_data, coordinator.api_client.api_url
        )

        # Only set via_device for non-gateway devices
        if "gateway" not in device_type and "router" not in device_type:
            # For switches and other devices, use uplink device if available
            if uplink_mac:
                di["via_device"] = (DOMAIN, uplink_mac)
            # No fallback - if no uplink, device is standalone

        self._attr_device_info = di

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        device_data = self.coordinator.data.get("devices", {}).get(self._device_mac)
        if device_data is None:
            return None
        return self.entity_description.value_fn(device_data)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False

        device_data = self.coordinator.data.get("devices", {}).get(self._device_mac)
        if device_data is None:
            return False

        return self.entity_description.available_fn(device_data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        if self.entity_description.attrs_fn is None:
            return None
        device_data = self.coordinator.data.get("devices", {}).get(self._device_mac)
        if device_data is None:
            return None
        return self.entity_description.attrs_fn(device_data)


class OmadaDeviceUptimeSensor(OmadaDeviceSensor):
    """Device uptime sensor with anti-spam hysteresis.

    Applies ceil-to-30s snapping and a 60-second hysteresis window to prevent
    HA recorder / activity-log spam, and detects device reboots so the UI
    updates promptly.
    """

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
        description: OmadaSensorEntityDescription,
        device_mac: str,
    ) -> None:
        """Initialize the uptime sensor with per-entity cached state."""
        super().__init__(
            coordinator=coordinator,
            description=description,
            device_mac=device_mac,
        )
        self._last_published_boot_ts: dt.datetime | None = None
        self._last_uptime_seconds: int | None = None

    @property
    def native_value(self) -> StateType:
        """Return a stable boot timestamp, suppressing minor jitter."""
        device_data = self.coordinator.data.get("devices", {}).get(self._device_mac)
        if device_data is None:
            return None
        uptime_seconds = device_data.get("uptime")
        if uptime_seconds is None:
            return None

        now = dt_util.utcnow().replace(microsecond=0)
        candidate = _ceil_to_30s(now - dt.timedelta(seconds=uptime_seconds))

        last_ts = self._last_published_boot_ts
        last_up = self._last_uptime_seconds
        self._last_uptime_seconds = uptime_seconds

        if last_ts is None:
            self._last_published_boot_ts = candidate
            return candidate  # type: ignore[return-value]

        # Reboot detection: device uptime dropped significantly.
        if (
            last_up is not None
            and uptime_seconds < last_up - _UPTIME_REBOOT_THRESHOLD_SECONDS
        ):
            self._last_published_boot_ts = candidate
            return candidate  # type: ignore[return-value]

        # Hysteresis: suppress updates smaller than the configured threshold.
        if abs((candidate - last_ts).total_seconds()) >= _UPTIME_MIN_DELTA_SECONDS:
            self._last_published_boot_ts = candidate
            return candidate  # type: ignore[return-value]

        # No significant change: return the cached value.
        return last_ts  # type: ignore[return-value]


class OmadaSiteSensor(OmadaEntity[OmadaSiteCoordinator], SensorEntity):
    """Representation of an Omada site-level aggregation sensor."""

    entity_description: OmadaSiteSensorEntityDescription

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
        description: OmadaSiteSensorEntityDescription,
    ) -> None:
        """Initialize a site-level sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        site_id = coordinator.site_id
        self._attr_unique_id = f"site_{site_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"site_{site_id}")},
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)


class OmadaThreatHeatmapSensor(
    OmadaEntity[OmadaThreatHeatmapCoordinator], SensorEntity
):
    """Sensor exposing aggregated threat heatmap points for a site/window."""

    entity_description: SensorEntityDescription

    def __init__(self, coordinator: OmadaThreatHeatmapCoordinator) -> None:
        """Initialize the threat heatmap sensor.

        Args:
            coordinator: Threat heatmap coordinator for one site/window

        """
        super().__init__(coordinator)
        window = coordinator.window
        self.entity_description = SensorEntityDescription(
            key=f"threat_heatmap_{window}",
            translation_key=f"threat_heatmap_{window}",
            icon=ICON_THREAT_HEATMAP,
            native_unit_of_measurement="threats",
            state_class=SensorStateClass.MEASUREMENT,
        )
        self._attr_unique_id = f"site_{coordinator.site_id}_threat_heatmap_{window}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"site_{coordinator.site_id}")},
        )

    @property
    def native_value(self) -> StateType:
        """Return the raw threat row count for the window."""
        return self.coordinator.data.get("total_rows")

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        return bool(self.coordinator.data.get("available", False))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the heatmap attribute contract consumed by the custom card."""
        data = self.coordinator.data
        return {
            "source": data["source"],
            "site_id": data["site_id"],
            "site_name": data["site_name"],
            "window": data["window"],
            "window_start": data["window_start"],
            "window_end": data["window_end"],
            "total_rows": data["total_rows"],
            "fetched_rows": data["fetched_rows"],
            "skipped_rows": data["skipped_rows"],
            "max": data["max"],
            "points": data["points"],
        }


class OmadaClientSensor(OmadaEntity[OmadaClientCoordinator], SensorEntity):
    """Representation of an Omada client sensor."""

    entity_description: OmadaSensorEntityDescription

    def __init__(
        self,
        coordinator: OmadaClientCoordinator,
        description: OmadaSensorEntityDescription,
        client_mac: str,
    ) -> None:
        """Initialize the client sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._client_mac = client_mac
        self._attr_unique_id = f"{client_mac}_{description.key}"

        # Set device info
        client_data = coordinator.data.get(client_mac, {})

        # Determine parent device (AP, switch, or gateway)
        parent_device_mac = None
        if client_data.get("wireless") and client_data.get("ap_mac"):
            # Wireless client connected to AP
            parent_device_mac = client_data.get("ap_mac")
        elif client_data.get("switch_mac"):
            # Wired client connected to switch
            parent_device_mac = client_data.get("switch_mac")
        elif client_data.get("gateway_mac"):
            # Client connected to gateway
            parent_device_mac = client_data.get("gateway_mac")

        # Use parent device as via_device if identified, otherwise use site
        via_device = (
            (DOMAIN, parent_device_mac)
            if parent_device_mac
            else (DOMAIN, coordinator.site_id)
        )

        self._attr_device_info = build_client_device_info(
            client_mac, client_data, coordinator.api_client.api_url, via_device
        )
        # Only log device info once per client (for signal strength sensor)
        if description.key == "signal_strength":
            _LOGGER.debug(
                "Client device %s: parent=%s, via_device=%s",
                self._attr_device_info["name"],
                parent_device_mac,
                via_device,
            )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        client_data = self.coordinator.data.get(self._client_mac)
        if client_data is None:
            return None
        return self.entity_description.value_fn(client_data)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False

        client_data = self.coordinator.data.get(self._client_mac)
        if client_data is None:
            return False

        return self.entity_description.available_fn(client_data)


class OmadaClientUptimeSensor(OmadaClientSensor):
    """Client uptime sensor with anti-spam hysteresis.

    Mirrors ``OmadaDeviceUptimeSensor`` for client entities: applies
    ceil-to-30s snapping and a 60-second hysteresis window to prevent HA
    recorder / activity-log spam, and detects client reconnections.
    """

    def __init__(
        self,
        coordinator: OmadaClientCoordinator,
        description: OmadaSensorEntityDescription,
        client_mac: str,
    ) -> None:
        """Initialize the client uptime sensor with per-entity cached state."""
        super().__init__(
            coordinator=coordinator,
            description=description,
            client_mac=client_mac,
        )
        self._last_published_boot_ts: dt.datetime | None = None
        self._last_uptime_seconds: int | None = None

    @property
    def native_value(self) -> StateType:
        """Return a stable boot timestamp, suppressing minor jitter."""
        client_data = self.coordinator.data.get(self._client_mac)
        if client_data is None:
            return None
        uptime_seconds = client_data.get("uptime")
        if uptime_seconds is None:
            return None

        now = dt_util.utcnow().replace(microsecond=0)
        candidate = _ceil_to_30s(now - dt.timedelta(seconds=uptime_seconds))

        last_ts = self._last_published_boot_ts
        last_up = self._last_uptime_seconds
        self._last_uptime_seconds = uptime_seconds

        if last_ts is None:
            self._last_published_boot_ts = candidate
            return candidate  # type: ignore[return-value]

        # Reconnect detection: client uptime dropped significantly.
        if (
            last_up is not None
            and uptime_seconds < last_up - _UPTIME_REBOOT_THRESHOLD_SECONDS
        ):
            self._last_published_boot_ts = candidate
            return candidate  # type: ignore[return-value]

        # Hysteresis: suppress updates smaller than the configured threshold.
        if abs((candidate - last_ts).total_seconds()) >= _UPTIME_MIN_DELTA_SECONDS:
            self._last_published_boot_ts = candidate
            return candidate  # type: ignore[return-value]

        # No significant change: return the cached value.
        return last_ts  # type: ignore[return-value]


class OmadaPoeBudgetSensor(OmadaEntity[OmadaSiteCoordinator], SensorEntity):
    """Sensor for per-switch PoE power budget metrics."""

    entity_description: OmadaSensorEntityDescription

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
        description: OmadaSensorEntityDescription,
        switch_mac: str,
    ) -> None:
        """Initialize the PoE budget sensor.

        Args:
            coordinator: Site coordinator that provides PoE budget data
            description: Sensor entity description
            switch_mac: MAC address of the switch

        """
        super().__init__(coordinator)
        self.entity_description = description
        self._switch_mac = switch_mac
        self._attr_unique_id = f"{switch_mac}_{description.key}"

        # Link to the parent switch device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, switch_mac)},
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        budget_data = self.coordinator.data.get("poe_budget", {}).get(self._switch_mac)
        if budget_data is None:
            return None
        return self.entity_description.value_fn(budget_data)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False

        budget_data = self.coordinator.data.get("poe_budget", {}).get(self._switch_mac)
        if budget_data is None:
            return False

        return self.entity_description.available_fn(budget_data)


# PoE display type mapping: max wattage per PoE standard
POE_DISPLAY_TYPES: dict[int, str] = {
    -1: "Not Supported",
    0: "PoE",
    1: "PoE (4W)",
    2: "PoE (7W)",
    3: "PoE (15.4W)",
    4: "PoE+ (30W)",
    5: "PoE++ (45W)",
    6: "PoE++ (60W)",
    7: "PoE++ (75W)",
    8: "PoE++ (90W)",
    9: "PoE++ (100W)",
}


class OmadaPoeSensor(OmadaEntity[OmadaSiteCoordinator], SensorEntity):
    """Sensor for PoE power consumption on a switch port."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_suggested_display_precision = 1
    _attr_icon = ICON_POE

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
        port_key: str,
    ) -> None:
        """Initialize the PoE sensor.

        Args:
            coordinator: Site coordinator that provides PoE data
            port_key: Key in poe_ports dict (format: switchMac_portNum)

        """
        super().__init__(coordinator)
        self._port_key = port_key

        port_data = coordinator.data.get("poe_ports", {}).get(port_key, {})
        switch_mac = port_data.get("switch_mac", "")
        port_num = port_data.get("port", 0)
        port_name = port_data.get("port_name", f"Port {port_num}")

        self._attr_unique_id = f"{switch_mac}_port{port_num}_poe_power"
        self._attr_translation_key = "poe_power"
        self._attr_translation_placeholders = {"port_name": port_name}

        # Link to the parent switch device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, switch_mac)},
        )

    @property
    def native_value(self) -> float | None:
        """Return PoE power consumption in watts."""
        port_data = self.coordinator.data.get("poe_ports", {}).get(self._port_key)
        if port_data is None:
            return None
        power: float = port_data.get("power", 0.0)
        return power

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        port_data = self.coordinator.data.get("poe_ports", {}).get(self._port_key)
        if port_data is None:
            return {}

        attrs: dict[str, Any] = {
            "port": port_data.get("port"),
            "port_name": port_data.get("port_name"),
            "poe_enabled": port_data.get("poe_enabled"),
            "voltage": port_data.get("voltage"),
            "current": port_data.get("current"),
        }

        # Add PD class if present
        if pd_class := port_data.get("pd_class"):
            attrs["pd_class"] = pd_class

        # Add PoE standard description
        poe_type = port_data.get("poe_display_type", -1)
        attrs["poe_standard"] = POE_DISPLAY_TYPES.get(poe_type, "Unknown")

        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False

        port_data = self.coordinator.data.get("poe_ports", {}).get(self._port_key)
        return port_data is not None


class OmadaClientAppTrafficSensor(
    OmadaEntity[OmadaAppTrafficCoordinator],
    SensorEntity,
):
    """Representation of an Omada client application traffic sensor."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self,
        coordinator: OmadaAppTrafficCoordinator,
        client_mac: str,
        app_id: str,
        app_name: str,
        metric_type: str,
    ) -> None:
        """Initialize the app traffic sensor."""
        super().__init__(coordinator)
        self._client_mac = client_mac
        self._app_id = app_id
        self._app_name = app_name
        self._metric_type = metric_type  # "upload" or "download"

        # Create unique ID
        self._attr_unique_id = f"{client_mac}_{app_id}_{metric_type}_app_traffic"

        # Set name based on metric type
        metric_key = "app_upload" if metric_type == "upload" else "app_download"
        self._attr_translation_key = metric_key
        self._attr_translation_placeholders = {"app_name": app_name}

        # Set icon based on metric type
        self._attr_icon = (
            "mdi:upload-network" if metric_type == "upload" else "mdi:download-network"
        )

        # Get client data to set up device info
        # Note: coordinator.data structure is dict[client_mac][app_id] = {...}
        # We need to get client info from the client coordinator
        # For now, use the client MAC to link to the client device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, client_mac)},
        )

        # Initial unit (will be dynamically updated based on value)
        self._attr_native_unit_of_measurement = UnitOfInformation.BYTES
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor with auto-scaled value."""
        # Get data from coordinator
        client_data = self.coordinator.data.get(self._client_mac, {})
        app_data = client_data.get(self._app_id, {})

        # Get raw byte value
        raw_bytes = app_data.get(self._metric_type, 0)

        # Auto-scale and update unit
        scaled_value, unit = _auto_scale_bytes(raw_bytes)

        # Update unit dynamically
        if unit:
            self._attr_native_unit_of_measurement = unit

        return scaled_value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        client_data = self.coordinator.data.get(self._client_mac, {})
        app_data = client_data.get(self._app_id, {})

        attributes = {
            "application_id": self._app_id,
            "application_name": app_data.get("app_name", self._app_name),
            "raw_bytes": app_data.get(self._metric_type, 0),
        }

        # Add optional attributes if available
        if app_desc := app_data.get("app_description"):
            attributes["application_description"] = app_desc
        if family := app_data.get("family"):
            attributes["family"] = family

        # Add total traffic if available
        if total_traffic := app_data.get("traffic"):
            attributes["total_traffic_bytes"] = total_traffic
            scaled_total, total_unit = _auto_scale_bytes(total_traffic)
            if scaled_total and total_unit:
                attributes["total_traffic"] = f"{scaled_total:.2f} {total_unit}"

        return attributes

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False

        # Check if we have data for this client and app
        client_data = self.coordinator.data.get(self._client_mac, {})
        return self._app_id in client_data


class OmadaWanSensor(OmadaEntity[OmadaSiteCoordinator], SensorEntity):
    """Sensor for a WAN port metric on a gateway device."""

    entity_description: OmadaSensorEntityDescription

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
        description: OmadaSensorEntityDescription,
        gateway_mac: str,
        port_index: int,
        port_name: str,
    ) -> None:
        """Initialize the WAN port sensor.

        Args:
            coordinator: Site coordinator providing WAN status data
            description: Sensor entity description
            gateway_mac: MAC address of the gateway
            port_index: Index into the WAN ports list
            port_name: Human-readable port name (e.g. "WAN1")

        """
        super().__init__(coordinator)
        self.entity_description = description
        self._gateway_mac = gateway_mac
        self._port_index = port_index
        self._attr_unique_id = f"{gateway_mac}_wan{port_index}_{description.key}"
        self._attr_translation_key = description.key
        self._attr_translation_placeholders = {"port_name": port_name}

        # Link to the parent gateway device.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, gateway_mac)},
        )

    def _get_port_data(self) -> dict[str, Any] | None:
        """Return the WAN port data dict, or None if unavailable."""
        ports = self.coordinator.data.get("wan_status", {}).get(self._gateway_mac, [])
        if self._port_index < len(ports):
            return ports[self._port_index]  # type: ignore[no-any-return]
        return None

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        port_data = self._get_port_data()
        if port_data is None:
            return None
        return self.entity_description.value_fn(port_data)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        port_data = self._get_port_data()
        if port_data is None:
            return False
        return self.entity_description.available_fn(port_data)


class OmadaWanSpeedSensor(OmadaEntity[OmadaSiteCoordinator], SensorEntity):
    """Sensor for a WAN speed test metric on a gateway device."""

    entity_description: OmadaSensorEntityDescription

    def __init__(
        self,
        coordinator: OmadaSiteCoordinator,
        description: OmadaSensorEntityDescription,
        gateway_mac: str,
    ) -> None:
        """Initialize the WAN speed test sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._gateway_mac = gateway_mac
        self._attr_unique_id = f"{gateway_mac}_{description.key}"
        self._attr_translation_key = description.key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, gateway_mac)},
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        speed_data = self.coordinator.data.get("wan_speed_test", {})
        if not speed_data:
            return None
        return self.entity_description.value_fn(speed_data)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        speed_data = self.coordinator.data.get("wan_speed_test", {})
        if not speed_data:
            return False
        return self.entity_description.available_fn(speed_data)


class OmadaDeviceTrafficSensor(OmadaEntity[OmadaDeviceStatsCoordinator], SensorEntity):
    """Sensor for daily device traffic totals."""

    entity_description: OmadaSensorEntityDescription

    def __init__(
        self,
        coordinator: OmadaDeviceStatsCoordinator,
        description: OmadaSensorEntityDescription,
        device_mac: str,
    ) -> None:
        """Initialize the device traffic sensor.

        Args:
            coordinator: Device stats coordinator providing daily data
            description: Sensor entity description
            device_mac: MAC address of the device

        """
        super().__init__(coordinator)
        self.entity_description = description
        self._device_mac = device_mac
        self._attr_unique_id = f"{device_mac}_{description.key}"

        # Link to the parent infrastructure device.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_mac)},
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        device_data = self.coordinator.data.get(self._device_mac)
        if device_data is None:
            return None
        return self.entity_description.value_fn(device_data)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        device_data = self.coordinator.data.get(self._device_mac)
        if device_data is None:
            return False
        return self.entity_description.available_fn(device_data)
