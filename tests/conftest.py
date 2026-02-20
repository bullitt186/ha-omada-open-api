"""Fixtures for Omada Open API tests."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

from custom_components.omada_open_api.const import (
    CONF_ACCESS_TOKEN,
    CONF_API_URL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_OMADA_ID,
    CONF_REFRESH_TOKEN,
    CONF_SELECTED_APPLICATIONS,
    CONF_SELECTED_CLIENTS,
    CONF_SELECTED_SITES,
    CONF_TOKEN_EXPIRES_AT,
)

pytest_plugins = "pytest_homeassistant_custom_component"

# ---------------------------------------------------------------------------
# Common test data
# ---------------------------------------------------------------------------

TEST_API_URL = "https://test-controller.example.com"
TEST_OMADA_ID = "test_omada_id"
TEST_CLIENT_ID = "test_client_id"
TEST_CLIENT_SECRET = "test_client_secret"
TEST_ACCESS_TOKEN = "test_access_token"
TEST_REFRESH_TOKEN = "test_refresh_token"
TEST_SITE_ID = "site_001"
TEST_SITE_NAME = "Main Office"


def _future_token_expiry() -> str:
    """Return an ISO timestamp 1 hour in the future."""
    return (dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)).isoformat()


SAMPLE_DEVICE_AP = {
    "mac": "AA-BB-CC-DD-EE-01",
    "name": "Office AP",
    "model": "EAP660 HD",
    "modelName": "EAP660 HD",
    "type": "ap",
    "status": 14,
    "statusCategory": 1,
    "detailStatus": 14,
    "ip": "192.168.1.10",
    "firmwareVersion": "1.2.3",
    "cpuUtil": 15,
    "memUtil": 45,
    "clientNum": 12,
    "uptime": "2day(s) 5h 30m 10s",
    "sn": "SN-AP-001",
    "active": True,
}

SAMPLE_DEVICE_SWITCH = {
    "mac": "AA-BB-CC-DD-EE-02",
    "name": "Core Switch",
    "model": "TL-SG3428X",
    "type": "switch",
    "status": 14,
    "statusCategory": 1,
    "detailStatus": 14,
    "ip": "192.168.1.2",
    "firmwareVersion": "2.0.0",
    "cpuUtil": 5,
    "memUtil": 30,
    "clientNum": 25,
    "uptime": 90000,
    "sn": "SN-SW-001",
    "active": True,
}

SAMPLE_DEVICE_GATEWAY = {
    "mac": "AA-BB-CC-DD-EE-03",
    "name": "Main Gateway",
    "model": "ER8411",
    "type": "gateway",
    "status": 14,
    "statusCategory": 1,
    "detailStatus": 14,
    "ip": "192.168.1.1",
    "publicIp": "1.2.3.4",
    "firmwareVersion": "3.0.0",
    "cpuUtil": 10,
    "memUtil": 55,
    "clientNum": 50,
    "uptime": 360000,
    "sn": "SN-GW-001",
    "active": True,
}

SAMPLE_UPLINK_INFO = [
    {
        "deviceMac": "AA-BB-CC-DD-EE-01",
        "uplinkDeviceMac": "AA-BB-CC-DD-EE-02",
        "uplinkDeviceName": "Core Switch",
        "uplinkDevicePort": 5,
        "linkSpeed": 3,
        "duplex": True,
    },
    {
        "deviceMac": "AA-BB-CC-DD-EE-02",
        "uplinkDeviceMac": "AA-BB-CC-DD-EE-03",
        "uplinkDeviceName": "Main Gateway",
        "uplinkDevicePort": 1,
        "linkSpeed": 3,
        "duplex": True,
    },
]

SAMPLE_CLIENT_WIRELESS = {
    "mac": "11-22-33-44-55-AA",
    "name": "Phone",
    "hostName": "phone-host",
    "ip": "192.168.1.100",
    "active": True,
    "wireless": True,
    "ssid": "MyWiFi",
    "signalLevel": -55,
    "rssi": -55,
    "snr": 35,
    "apName": "Office AP",
    "apMac": "AA-BB-CC-DD-EE-01",
    "channel": 36,
    "uptime": 3600,
    "trafficDown": 1_500_000_000,
    "trafficUp": 500_000_000,
    "activity": 2_500_000,
    "uploadActivity": 1_200_000,
    "powerSave": True,
    "blocked": False,
    "connectType": 1,
    "wifiMode": 6,
    "rxRate": 866_000,
    "txRate": 433_000,
    "signalRank": 4,
    "healthScore": 85,
    "vendor": "Apple",
    "deviceType": "iPhone",
    "osName": "iOS",
}

SAMPLE_CLIENT_WIRED = {
    "mac": "11-22-33-44-55-BB",
    "name": "Desktop",
    "hostName": "desktop-host",
    "ip": "192.168.1.101",
    "active": True,
    "wireless": False,
    "switchName": "Core Switch",
    "switchMac": "AA-BB-CC-DD-EE-02",
    "port": 10,
    "uptime": 7200,
    "trafficDown": 5_000_000_000,
    "trafficUp": 2_000_000_000,
    "activity": 5_000_000,
    "uploadActivity": 3_000_000,
    "blocked": False,
    "networkName": "LAN",
    "vid": 1,
    "portName": "Port 10",
    "vendor": "Dell",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: Generator,
) -> Generator:
    """Enable custom integrations for all tests."""
    return


@pytest.fixture
def mock_config_entry_data() -> dict:
    """Return standard config entry data."""
    return {
        CONF_API_URL: TEST_API_URL,
        CONF_OMADA_ID: TEST_OMADA_ID,
        CONF_CLIENT_ID: TEST_CLIENT_ID,
        CONF_CLIENT_SECRET: TEST_CLIENT_SECRET,
        CONF_ACCESS_TOKEN: TEST_ACCESS_TOKEN,
        CONF_REFRESH_TOKEN: TEST_REFRESH_TOKEN,
        CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
        CONF_SELECTED_SITES: [TEST_SITE_ID],
        CONF_SELECTED_CLIENTS: [],
        CONF_SELECTED_APPLICATIONS: [],
    }


@pytest.fixture
def mock_api_client() -> MagicMock:
    """Create a mock OmadaApiClient."""
    client = MagicMock()
    client.api_url = TEST_API_URL

    # Default happy-path return values
    client.get_sites = AsyncMock(
        return_value=[{"siteId": TEST_SITE_ID, "name": TEST_SITE_NAME}]
    )
    client.get_devices = AsyncMock(
        return_value=[SAMPLE_DEVICE_AP, SAMPLE_DEVICE_SWITCH, SAMPLE_DEVICE_GATEWAY]
    )
    client.get_device_uplink_info = AsyncMock(return_value=SAMPLE_UPLINK_INFO)
    client.get_clients = AsyncMock(
        return_value={
            "data": [SAMPLE_CLIENT_WIRELESS, SAMPLE_CLIENT_WIRED],
            "totalRows": 2,
            "currentPage": 1,
        }
    )
    client.get_client_app_traffic = AsyncMock(return_value=[])
    client.get_applications = AsyncMock(
        return_value={"data": [], "totalRows": 0, "currentPage": 1}
    )
    client.get_switch_ports_poe = AsyncMock(return_value=[])
    client.get_poe_usage = AsyncMock(return_value=[])
    client.get_device_client_stats = AsyncMock(return_value=[])
    client.reboot_device = AsyncMock()
    client.reconnect_client = AsyncMock()
    client.start_wlan_optimization = AsyncMock()
    client.block_client = AsyncMock()
    client.unblock_client = AsyncMock()
    client.get_firmware_info = AsyncMock(return_value={})
    client.start_online_upgrade = AsyncMock(return_value={})
    client.get_led_setting = AsyncMock(return_value={"enable": True})
    client.set_led_setting = AsyncMock(return_value={})
    client.locate_device = AsyncMock()
    client.get_ap_radios = AsyncMock(return_value={})
    return client


# ---------------------------------------------------------------------------
# PoE sample data
# ---------------------------------------------------------------------------

SAMPLE_POE_PORT_ACTIVE = {
    "port": 1,
    "switchMac": "AA-BB-CC-DD-EE-02",
    "switchName": "Core Switch",
    "portName": "Port 1",
    "supportPoe": True,
    "poe": 1,
    "power": 12.5,
    "voltage": 53.2,
    "current": 235.0,
    "poeStatus": 1.0,
    "pdClass": "Class 4",
    "poeDisplayType": 4,
    "connectedStatus": 0,
    "switchSupportPoe": 1,
}

SAMPLE_POE_PORT_INACTIVE = {
    "port": 2,
    "switchMac": "AA-BB-CC-DD-EE-02",
    "switchName": "Core Switch",
    "portName": "Port 2",
    "supportPoe": True,
    "poe": 0,
    "power": 0.0,
    "voltage": 0.0,
    "current": 0.0,
    "poeStatus": 0.0,
    "pdClass": "",
    "poeDisplayType": 4,
    "connectedStatus": 1,
    "switchSupportPoe": 1,
}

SAMPLE_POE_PORT_NOT_SUPPORTED = {
    "port": 3,
    "switchMac": "AA-BB-CC-DD-EE-02",
    "switchName": "Core Switch",
    "portName": "Port 3",
    "supportPoe": False,
    "poe": 0,
    "power": 0.0,
    "voltage": 0.0,
    "current": 0.0,
    "poeStatus": 0.0,
    "pdClass": "",
    "poeDisplayType": -1,
    "connectedStatus": 1,
    "switchSupportPoe": 1,
}

SAMPLE_POE_PORT_SWITCH_NOT_SUPPORTED = {
    "port": 1,
    "switchMac": "AA-BB-CC-DD-EE-99",
    "switchName": "Non-PoE Switch",
    "portName": "Port 1",
    "supportPoe": True,
    "poe": 0,
    "power": 0.0,
    "voltage": 0.0,
    "current": 0.0,
    "poeStatus": 0.0,
    "pdClass": "",
    "poeDisplayType": -1,
    "connectedStatus": 1,
    "switchSupportPoe": 0,
}

# PoE budget (dashboard/poe-usage) sample data
SAMPLE_POE_USAGE = {
    "mac": "AA-BB-CC-DD-EE-02",
    "name": "Core Switch",
    "portNum": 24,
    "totalPowerUsed": 45,
    "totalPercentUsed": 18.75,
    "totalPower": 240,
}

SAMPLE_POE_USAGE_SECOND = {
    "mac": "AA-BB-CC-DD-EE-99",
    "name": "Edge Switch",
    "portNum": 8,
    "totalPowerUsed": 0,
    "totalPercentUsed": 0.0,
    "totalPower": 62,
}
