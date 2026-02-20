"""Tests for OmadaClientSensor entity."""

from __future__ import annotations

import datetime as _dt
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.omada_open_api.clients import process_client
from custom_components.omada_open_api.const import DOMAIN
from custom_components.omada_open_api.coordinator import OmadaClientCoordinator
from custom_components.omada_open_api.sensor import CLIENT_SENSORS, OmadaClientSensor

from .conftest import (
    SAMPLE_CLIENT_WIRED,
    SAMPLE_CLIENT_WIRELESS,
    TEST_SITE_ID,
    TEST_SITE_NAME,
)

WIRELESS_MAC = "11-22-33-44-55-AA"
WIRED_MAC = "11-22-33-44-55-BB"


def _build_client_coordinator_data(
    clients: dict[str, dict] | None = None,
) -> dict:
    """Build coordinator data dict with processed clients."""
    return clients or {}


def _processed_wireless() -> dict:
    """Return processed wireless client data."""
    return process_client(SAMPLE_CLIENT_WIRELESS)


def _processed_wired() -> dict:
    """Return processed wired client data."""
    return process_client(SAMPLE_CLIENT_WIRED)


def _create_client_sensor(
    hass: HomeAssistant,
    client_mac: str,
    clients: dict[str, dict],
    description_key: str,
) -> OmadaClientSensor:
    """Create an OmadaClientSensor with a mock coordinator."""
    coordinator = OmadaClientCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        selected_client_macs=list(clients.keys()),
    )
    coordinator.data = _build_client_coordinator_data(clients)

    # Find the matching description
    description = next(d for d in CLIENT_SENSORS if d.key == description_key)

    return OmadaClientSensor(
        coordinator=coordinator,
        description=description,
        client_mac=client_mac,
    )


# ---------------------------------------------------------------------------
# Initialization & identity
# ---------------------------------------------------------------------------


async def test_client_sensor_unique_id(hass: HomeAssistant) -> None:
    """Test unique_id format for client sensor."""
    sensor = _create_client_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: _processed_wireless()},
        "connection_status",
    )
    assert sensor.unique_id == f"{WIRELESS_MAC}_connection_status"


async def test_client_sensor_name(hass: HomeAssistant) -> None:
    """Test sensor name is set from description."""
    sensor = _create_client_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: _processed_wireless()},
        "ip_address",
    )
    assert sensor.entity_description.name == "IP Address"


async def test_client_sensor_device_info_wireless(hass: HomeAssistant) -> None:
    """Test device_info links to parent AP for wireless client."""
    sensor = _create_client_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: _processed_wireless()},
        "connection_status",
    )
    device_info = sensor._attr_device_info  # noqa: SLF001
    assert (DOMAIN, WIRELESS_MAC) in device_info["identifiers"]
    assert device_info["name"] == "Phone"
    assert device_info["manufacturer"] == "Apple"
    assert device_info["via_device"] == (DOMAIN, "AA-BB-CC-DD-EE-01")


async def test_client_sensor_device_info_wired(hass: HomeAssistant) -> None:
    """Test device_info links to parent switch for wired client."""
    sensor = _create_client_sensor(
        hass,
        WIRED_MAC,
        {WIRED_MAC: _processed_wired()},
        "connection_status",
    )
    device_info = sensor._attr_device_info  # noqa: SLF001
    assert (DOMAIN, WIRED_MAC) in device_info["identifiers"]
    assert device_info["name"] == "Desktop"
    assert device_info["manufacturer"] == "Dell"
    assert device_info["via_device"] == (DOMAIN, "AA-BB-CC-DD-EE-02")


# ---------------------------------------------------------------------------
# Existing sensors - basic value checks
# ---------------------------------------------------------------------------


async def test_connection_status_connected(hass: HomeAssistant) -> None:
    """Test connection_status returns Connected for active client."""
    sensor = _create_client_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: _processed_wireless()},
        "connection_status",
    )
    assert sensor.native_value == "Connected"


async def test_connection_status_disconnected(hass: HomeAssistant) -> None:
    """Test connection_status returns Disconnected for inactive client."""
    data = _processed_wireless()
    data["active"] = False
    sensor = _create_client_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: data},
        "connection_status",
    )
    assert sensor.native_value == "Disconnected"


async def test_ip_address_sensor(hass: HomeAssistant) -> None:
    """Test ip_address sensor returns IP."""
    sensor = _create_client_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: _processed_wireless()},
        "ip_address",
    )
    assert sensor.native_value == "192.168.1.100"


async def test_ssid_sensor_wireless(hass: HomeAssistant) -> None:
    """Test SSID sensor returns SSID for wireless client."""
    sensor = _create_client_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: _processed_wireless()},
        "ssid",
    )
    assert sensor.native_value == "MyWiFi"
    assert sensor.available is True


async def test_ssid_sensor_unavailable_wired(hass: HomeAssistant) -> None:
    """Test SSID sensor is unavailable for wired client."""
    sensor = _create_client_sensor(
        hass,
        WIRED_MAC,
        {WIRED_MAC: _processed_wired()},
        "ssid",
    )
    assert sensor.available is False


async def test_connected_to_wireless(hass: HomeAssistant) -> None:
    """Test connected_to returns AP name for wireless client."""
    sensor = _create_client_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: _processed_wireless()},
        "connected_to",
    )
    assert sensor.native_value == "Office AP"


async def test_connected_to_wired(hass: HomeAssistant) -> None:
    """Test connected_to returns switch name for wired client."""
    sensor = _create_client_sensor(
        hass,
        WIRED_MAC,
        {WIRED_MAC: _processed_wired()},
        "connected_to",
    )
    assert sensor.native_value == "Core Switch"


# ---------------------------------------------------------------------------
# New traffic sensors
# ---------------------------------------------------------------------------


async def test_downloaded_sensor_wireless(hass: HomeAssistant) -> None:
    """Test downloaded sensor converts bytes to MB."""
    sensor = _create_client_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: _processed_wireless()},
        "downloaded",
    )
    # 1_500_000_000 bytes / 1_000_000 = 1500.0 MB
    assert sensor.native_value == 1500.0
    assert sensor.available is True


async def test_downloaded_sensor_wired(hass: HomeAssistant) -> None:
    """Test downloaded sensor for wired client."""
    sensor = _create_client_sensor(
        hass,
        WIRED_MAC,
        {WIRED_MAC: _processed_wired()},
        "downloaded",
    )
    # 5_000_000_000 bytes / 1_000_000 = 5000.0 MB
    assert sensor.native_value == 5000.0


async def test_uploaded_sensor_wireless(hass: HomeAssistant) -> None:
    """Test uploaded sensor converts bytes to MB."""
    sensor = _create_client_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: _processed_wireless()},
        "uploaded",
    )
    # 500_000_000 bytes / 1_000_000 = 500.0 MB
    assert sensor.native_value == 500.0


async def test_uploaded_sensor_wired(hass: HomeAssistant) -> None:
    """Test uploaded sensor for wired client."""
    sensor = _create_client_sensor(
        hass,
        WIRED_MAC,
        {WIRED_MAC: _processed_wired()},
        "uploaded",
    )
    # 2_000_000_000 bytes / 1_000_000 = 2000.0 MB
    assert sensor.native_value == 2000.0


async def test_downloaded_unavailable_when_none(hass: HomeAssistant) -> None:
    """Test downloaded sensor unavailable when traffic_down is None."""
    data = _processed_wireless()
    data["traffic_down"] = None
    sensor = _create_client_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: data},
        "downloaded",
    )
    assert sensor.available is False
    assert sensor.native_value is None


async def test_rx_activity_sensor(hass: HomeAssistant) -> None:
    """Test RX activity sensor converts bytes/s to MB/s."""
    sensor = _create_client_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: _processed_wireless()},
        "rx_activity",
    )
    # 2_500_000 bytes/s / 1_000_000 = 2.50 MB/s
    assert sensor.native_value == 2.5


async def test_tx_activity_sensor(hass: HomeAssistant) -> None:
    """Test TX activity sensor converts bytes/s to MB/s."""
    sensor = _create_client_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: _processed_wireless()},
        "tx_activity",
    )
    # 1_200_000 bytes/s / 1_000_000 = 1.20 MB/s
    assert sensor.native_value == 1.2


async def test_rx_activity_unavailable_when_none(hass: HomeAssistant) -> None:
    """Test RX activity sensor defaults to 0 for active client with None activity."""
    data = _processed_wireless()
    data["activity"] = None
    sensor = _create_client_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: data},
        "rx_activity",
    )
    # Active client with None activity should be available and default to 0.
    assert sensor.available is True
    assert sensor.native_value == 0.0


# ---------------------------------------------------------------------------
# RSSI and SNR sensors
# ---------------------------------------------------------------------------


async def test_rssi_sensor_wireless(hass: HomeAssistant) -> None:
    """Test RSSI sensor returns value for wireless client."""
    sensor = _create_client_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: _processed_wireless()},
        "rssi",
    )
    assert sensor.native_value == -55
    assert sensor.available is True


async def test_rssi_sensor_unavailable_wired(hass: HomeAssistant) -> None:
    """Test RSSI sensor unavailable for wired client."""
    sensor = _create_client_sensor(
        hass,
        WIRED_MAC,
        {WIRED_MAC: _processed_wired()},
        "rssi",
    )
    assert sensor.available is False


async def test_snr_sensor_wireless(hass: HomeAssistant) -> None:
    """Test SNR sensor returns value for wireless client."""
    sensor = _create_client_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: _processed_wireless()},
        "snr",
    )
    assert sensor.native_value == 35
    assert sensor.available is True


async def test_snr_sensor_unavailable_wired(hass: HomeAssistant) -> None:
    """Test SNR sensor unavailable for wired client."""
    sensor = _create_client_sensor(
        hass,
        WIRED_MAC,
        {WIRED_MAC: _processed_wired()},
        "snr",
    )
    assert sensor.available is False


# ---------------------------------------------------------------------------
# Uptime sensor
# ---------------------------------------------------------------------------


async def test_client_uptime_wireless(hass: HomeAssistant) -> None:
    """Test uptime sensor returns ISO timestamp (boot time)."""
    sensor = _create_client_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: _processed_wireless()},
        "client_uptime",
    )
    value = sensor.native_value
    assert isinstance(value, str)
    parsed = _dt.datetime.fromisoformat(value)
    assert parsed.tzinfo is not None or "T" in value


async def test_client_uptime_wired(hass: HomeAssistant) -> None:
    """Test uptime sensor for wired client returns ISO timestamp."""
    sensor = _create_client_sensor(
        hass,
        WIRED_MAC,
        {WIRED_MAC: _processed_wired()},
        "client_uptime",
    )
    value = sensor.native_value
    assert isinstance(value, str)
    parsed = _dt.datetime.fromisoformat(value)
    assert parsed.tzinfo is not None or "T" in value


async def test_client_uptime_unavailable_when_none(hass: HomeAssistant) -> None:
    """Test uptime sensor unavailable when uptime is None."""
    data = _processed_wireless()
    data["uptime"] = None
    sensor = _create_client_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: data},
        "client_uptime",
    )
    assert sensor.available is False


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


async def test_client_sensor_missing_client_data(hass: HomeAssistant) -> None:
    """Test sensor returns None when client not in coordinator data."""
    sensor = _create_client_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: _processed_wireless()},
        "ip_address",
    )
    # Remove client from data to simulate disappearance
    sensor.coordinator.data = {}
    assert sensor.native_value is None
    assert sensor.available is False


async def test_client_sensor_coordinator_failure(hass: HomeAssistant) -> None:
    """Test sensor unavailable when coordinator update fails."""
    sensor = _create_client_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: _processed_wireless()},
        "ip_address",
    )
    sensor.coordinator.last_update_success = False
    assert sensor.available is False


# ---------------------------------------------------------------------------
# Activity availability for inactive clients
# ---------------------------------------------------------------------------


async def test_rx_activity_unavailable_when_inactive(hass: HomeAssistant) -> None:
    """Test RX activity sensor unavailable when client is inactive."""
    data = _processed_wireless()
    data["active"] = False
    sensor = _create_client_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: data},
        "rx_activity",
    )
    assert sensor.available is False


async def test_tx_activity_unavailable_when_inactive(hass: HomeAssistant) -> None:
    """Test TX activity sensor unavailable when client is inactive."""
    data = _processed_wireless()
    data["active"] = False
    sensor = _create_client_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: data},
        "tx_activity",
    )
    assert sensor.available is False


async def test_tx_activity_defaults_to_zero(hass: HomeAssistant) -> None:
    """Test TX activity sensor defaults to 0 when field is None."""
    data = _processed_wireless()
    data["upload_activity"] = None
    sensor = _create_client_sensor(
        hass,
        WIRELESS_MAC,
        {WIRELESS_MAC: data},
        "tx_activity",
    )
    assert sensor.available is True
    assert sensor.native_value == 0.0


async def test_signal_strength_unavailable_wired(hass: HomeAssistant) -> None:
    """Test signal_strength unavailable for wired client."""
    sensor = _create_client_sensor(
        hass,
        WIRED_MAC,
        {WIRED_MAC: _processed_wired()},
        "signal_strength",
    )
    assert sensor.available is False
