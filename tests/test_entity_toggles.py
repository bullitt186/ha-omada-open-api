"""Tests for granular entity type toggles in options flow (Issue #11)."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.omada_open_api.config_flow import OmadaOptionsFlowHandler
from custom_components.omada_open_api.const import (
    CONF_ACCESS_TOKEN,
    CONF_API_URL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_ENABLE_CLIENT_BANDWIDTH_SENSORS,
    CONF_ENABLE_CLIENT_BLOCK_SWITCH,
    CONF_ENABLE_CLIENT_RECONNECT_BUTTON,
    CONF_ENABLE_CLIENT_SIGNAL_SENSORS,
    CONF_ENABLE_DEVICE_BANDWIDTH_SENSORS,
    CONF_ENABLE_DEVICE_CLIENT_COUNT_SENSORS,
    CONF_ENABLE_DEVICE_DIAGNOSTIC_SENSORS,
    CONF_ENABLE_DEVICE_RADIO_UTILIZATION_SENSORS,
    CONF_ENABLE_THREAT_HEATMAP_SENSORS,
    CONF_ENABLE_VPN_SENSORS,
    CONF_ENABLE_WAN_SPEED_TEST,
    CONF_OMADA_ID,
    CONF_REFRESH_TOKEN,
    CONF_SELECTED_APPLICATIONS,
    CONF_SELECTED_CLIENTS,
    CONF_SELECTED_SITES,
    CONF_TOKEN_EXPIRES_AT,
    DOMAIN,
)
from custom_components.omada_open_api.coordinator import OmadaSiteCoordinator
from custom_components.omada_open_api.sensor import (
    _check_ap_band_entities,
    _excluded_device_sensor_keys,
)

from .conftest import (
    SAMPLE_DEVICE_AP,
    SAMPLE_DEVICE_GATEWAY,
    SAMPLE_DEVICE_SWITCH,
    TEST_API_URL,
    TEST_SITE_ID,
    TEST_SITE_NAME,
    _future_token_expiry,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


# ---------------------------------------------------------------------------
# Constants exist and have correct semantics
# ---------------------------------------------------------------------------


def test_toggle_constants_are_strings() -> None:
    """All toggle constants are string values."""
    assert isinstance(CONF_ENABLE_DEVICE_BANDWIDTH_SENSORS, str)
    assert isinstance(CONF_ENABLE_DEVICE_CLIENT_COUNT_SENSORS, str)
    assert isinstance(CONF_ENABLE_DEVICE_DIAGNOSTIC_SENSORS, str)
    assert isinstance(CONF_ENABLE_DEVICE_RADIO_UTILIZATION_SENSORS, str)
    assert isinstance(CONF_ENABLE_CLIENT_BANDWIDTH_SENSORS, str)
    assert isinstance(CONF_ENABLE_CLIENT_SIGNAL_SENSORS, str)
    assert isinstance(CONF_ENABLE_CLIENT_BLOCK_SWITCH, str)
    assert isinstance(CONF_ENABLE_CLIENT_RECONNECT_BUTTON, str)
    assert isinstance(CONF_ENABLE_VPN_SENSORS, str)
    assert isinstance(CONF_ENABLE_WAN_SPEED_TEST, str)


def test_toggle_constants_have_distinct_values() -> None:
    """All toggle constants have distinct string values."""
    values = [
        CONF_ENABLE_DEVICE_BANDWIDTH_SENSORS,
        CONF_ENABLE_DEVICE_CLIENT_COUNT_SENSORS,
        CONF_ENABLE_DEVICE_DIAGNOSTIC_SENSORS,
        CONF_ENABLE_DEVICE_RADIO_UTILIZATION_SENSORS,
        CONF_ENABLE_CLIENT_BANDWIDTH_SENSORS,
        CONF_ENABLE_CLIENT_SIGNAL_SENSORS,
        CONF_ENABLE_CLIENT_BLOCK_SWITCH,
        CONF_ENABLE_CLIENT_RECONNECT_BUTTON,
        CONF_ENABLE_VPN_SENSORS,
        CONF_ENABLE_WAN_SPEED_TEST,
    ]
    assert len(set(values)) == len(values)


# ---------------------------------------------------------------------------
# Options flow exposes the toggle steps
# ---------------------------------------------------------------------------


def test_options_flow_has_device_entity_settings_step() -> None:
    """OmadaOptionsFlowHandler has async_step_device_entity_settings."""
    assert hasattr(OmadaOptionsFlowHandler, "async_step_device_entity_settings")


def test_options_flow_has_client_entity_settings_step() -> None:
    """OmadaOptionsFlowHandler has async_step_client_entity_settings."""
    assert hasattr(OmadaOptionsFlowHandler, "async_step_client_entity_settings")


def test_options_flow_menu_includes_entity_settings() -> None:
    """The options flow init menu includes both entity settings steps."""
    source = inspect.getsource(
        OmadaOptionsFlowHandler.async_step_init  # type: ignore[attr-defined]
    )
    assert "device_entity_settings" in source
    assert "client_entity_settings" in source
    assert "site_entity_settings" in source


def test_options_flow_has_site_entity_settings_step() -> None:
    """OmadaOptionsFlowHandler has async_step_site_entity_settings."""
    assert hasattr(OmadaOptionsFlowHandler, "async_step_site_entity_settings")


def test_options_flow_has_gateway_entity_settings_step() -> None:
    """Gateway diagnostics and actions are configurable from options."""
    assert hasattr(OmadaOptionsFlowHandler, "async_step_gateway_entity_settings")
    source = inspect.getsource(
        OmadaOptionsFlowHandler.async_step_init  # type: ignore[attr-defined]
    )
    assert "gateway_entity_settings" in source


# ---------------------------------------------------------------------------
# Helper: shared mock API builder
# ---------------------------------------------------------------------------


def _build_mock_api(devices: list) -> AsyncMock:
    """Build a mock API client for integration tests."""
    mock = AsyncMock()
    mock.get_sites = AsyncMock(
        return_value=[{"siteId": TEST_SITE_ID, "name": TEST_SITE_NAME}]
    )
    mock.get_devices = AsyncMock(return_value=devices)
    mock.get_device_uplink_info = AsyncMock(return_value=[])
    mock.get_device_client_stats = AsyncMock(return_value=[])
    mock.get_ap_radios = AsyncMock(return_value={})
    mock.get_gateway_info = AsyncMock(return_value={})
    mock.get_site_ssids_comprehensive = AsyncMock(return_value=[])
    mock.get_ap_ssid_overrides = AsyncMock(return_value={"ssidOverrides": []})
    mock.get_poe_usage = AsyncMock(return_value=[])
    mock.get_switch_ports_poe = AsyncMock(return_value=[])
    mock.get_clients = AsyncMock(
        return_value={"data": [], "totalRows": 0, "currentPage": 1}
    )
    mock.get_gateway_wan_status = AsyncMock(return_value=[])
    mock.get_gateway_wan_speed_test_result = AsyncMock(return_value={})
    mock.get_vpn_s2s_stats = AsyncMock(return_value=[])
    mock.get_vpn_server_stats = AsyncMock(return_value=[])
    mock.get_vpn_client_stats = AsyncMock(return_value=[])
    mock.get_firmware_info = AsyncMock(return_value={})
    mock.get_led_setting = AsyncMock(return_value={"enable": True})
    mock.get_switch_port_details = AsyncMock(return_value=[])
    mock.get_ap_radio_config = AsyncMock(return_value={})
    mock.get_ap_led_setting = AsyncMock(return_value={})
    mock.set_ap_radio_enabled = AsyncMock()
    mock.get_wlan_optimization_status = AsyncMock(
        return_value={"status": 0, "beforeIndex": 55, "afterIndex": 80}
    )
    mock.get_device_stats = AsyncMock(return_value=[])
    mock.check_write_access = AsyncMock(return_value=True)
    mock.get_threat_management = AsyncMock(return_value=[])
    mock.api_url = TEST_API_URL
    return mock


def _build_entry(hass: HomeAssistant, options: dict, entry_id: str) -> MockConfigEntry:
    """Create and add a config entry with given options."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id=entry_id,
        data={
            CONF_API_URL: TEST_API_URL,
            CONF_OMADA_ID: "test_omada_id",
            CONF_CLIENT_ID: "test_client_id",
            CONF_CLIENT_SECRET: "test_secret",
            CONF_ACCESS_TOKEN: "tok",
            CONF_REFRESH_TOKEN: "rtok",
            CONF_TOKEN_EXPIRES_AT: _future_token_expiry(),
            CONF_SELECTED_SITES: [TEST_SITE_ID],
            CONF_SELECTED_CLIENTS: [],
            CONF_SELECTED_APPLICATIONS: [],
        },
        options={
            CONF_SELECTED_CLIENTS: [],
            CONF_SELECTED_APPLICATIONS: [],
            **options,
        },
    )
    entry.add_to_hass(hass)
    return entry


# ---------------------------------------------------------------------------
# Entity creation is skipped when toggles are off
# ---------------------------------------------------------------------------


async def test_device_bandwidth_sensors_skipped_when_disabled(
    hass: HomeAssistant,
) -> None:
    """Daily download/upload sensors not created when bandwidth toggle is False."""
    entry = _build_entry(
        hass, {CONF_ENABLE_DEVICE_BANDWIDTH_SENSORS: False}, "test_toggle_bw"
    )
    mock = _build_mock_api([SAMPLE_DEVICE_SWITCH, SAMPLE_DEVICE_GATEWAY])

    sw_mac = SAMPLE_DEVICE_SWITCH["mac"]
    gw_mac = SAMPLE_DEVICE_GATEWAY["mac"]

    with patch("custom_components.omada_open_api.OmadaApiClient", return_value=mock):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    reg = er.async_get(hass)
    assert reg.async_get_entity_id("sensor", DOMAIN, f"{sw_mac}_daily_download") is None
    assert reg.async_get_entity_id("sensor", DOMAIN, f"{gw_mac}_daily_download") is None


async def test_client_bandwidth_sensors_skipped_when_disabled(
    hass: HomeAssistant,
) -> None:
    """Client downloaded/uploaded/RX/TX sensors are not created when disabled.

    Regression test for GH #65: CONF_ENABLE_CLIENT_BANDWIDTH_SENSORS was
    defined and exposed in the options UI ("Bandwidth sensors (downloaded,
    uploaded, RX/TX activity rate)") but never actually read anywhere, so
    toggling it off had no effect at all.
    """
    client_mac = "11-22-33-44-55-AA"
    entry = _build_entry(
        hass,
        {
            CONF_ENABLE_CLIENT_BANDWIDTH_SENSORS: False,
            CONF_SELECTED_CLIENTS: [client_mac],
        },
        "test_toggle_client_bw",
    )
    mock = _build_mock_api([])
    mock.get_clients = AsyncMock(
        return_value={
            "data": [
                {
                    "mac": client_mac,
                    "name": "Phone",
                    "active": True,
                    "wireless": True,
                }
            ],
            "totalRows": 1,
            "currentPage": 1,
        }
    )

    with patch("custom_components.omada_open_api.OmadaApiClient", return_value=mock):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    reg = er.async_get(hass)
    assert reg.async_get_entity_id("sensor", DOMAIN, f"{client_mac}_downloaded") is None
    assert reg.async_get_entity_id("sensor", DOMAIN, f"{client_mac}_uploaded") is None
    assert (
        reg.async_get_entity_id("sensor", DOMAIN, f"{client_mac}_rx_activity") is None
    )
    assert (
        reg.async_get_entity_id("sensor", DOMAIN, f"{client_mac}_tx_activity") is None
    )
    # Unrelated client sensors are still created.
    assert (
        reg.async_get_entity_id("sensor", DOMAIN, f"{client_mac}_connection_status")
        is not None
    )


async def test_client_bandwidth_sensors_created_by_default(
    hass: HomeAssistant,
) -> None:
    """Client downloaded/uploaded/RX/TX sensors are created by default."""
    client_mac = "11-22-33-44-55-AB"
    entry = _build_entry(
        hass,
        {CONF_SELECTED_CLIENTS: [client_mac]},
        "test_toggle_client_bw_default",
    )
    mock = _build_mock_api([])
    mock.get_clients = AsyncMock(
        return_value={
            "data": [
                {
                    "mac": client_mac,
                    "name": "Phone",
                    "active": True,
                    "wireless": True,
                }
            ],
            "totalRows": 1,
            "currentPage": 1,
        }
    )

    with patch("custom_components.omada_open_api.OmadaApiClient", return_value=mock):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    reg = er.async_get(hass)
    assert (
        reg.async_get_entity_id("sensor", DOMAIN, f"{client_mac}_downloaded")
        is not None
    )


async def test_device_diagnostic_sensors_skipped_when_disabled(
    hass: HomeAssistant,
) -> None:
    """CPU/memory/uptime sensors not created when diagnostic toggle is False."""
    entry = _build_entry(
        hass, {CONF_ENABLE_DEVICE_DIAGNOSTIC_SENSORS: False}, "test_toggle_diag"
    )
    mock = _build_mock_api([SAMPLE_DEVICE_AP])

    ap_mac = SAMPLE_DEVICE_AP["mac"]

    with patch("custom_components.omada_open_api.OmadaApiClient", return_value=mock):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    reg = er.async_get(hass)
    assert reg.async_get_entity_id("sensor", DOMAIN, f"{ap_mac}_cpu_util") is None
    assert reg.async_get_entity_id("sensor", DOMAIN, f"{ap_mac}_mem_util") is None


@pytest.mark.parametrize("toggle_key", [CONF_ENABLE_DEVICE_BANDWIDTH_SENSORS])
async def test_toggle_defaults_to_true_on_upgrade(
    hass: HomeAssistant, toggle_key: str
) -> None:
    """When toggle option absent from entry (existing user on upgrade), defaults to True."""
    # No toggle options set — simulates existing user who hasn't seen the new options yet
    entry = _build_entry(hass, {}, "test_toggle_default")
    mock = _build_mock_api([SAMPLE_DEVICE_SWITCH])

    sw_mac = SAMPLE_DEVICE_SWITCH["mac"]

    with patch("custom_components.omada_open_api.OmadaApiClient", return_value=mock):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    reg = er.async_get(hass)
    # daily_download should be created (default on)
    assert (
        reg.async_get_entity_id("sensor", DOMAIN, f"{sw_mac}_daily_download")
        is not None
    )


async def test_threat_heatmap_sensors_created_by_default(
    hass: HomeAssistant,
) -> None:
    """Threat heatmap sensors are created when the toggle is unset (default True)."""
    entry = _build_entry(hass, {}, "test_threat_heatmap_default")
    mock = _build_mock_api([SAMPLE_DEVICE_AP])

    with patch("custom_components.omada_open_api.OmadaApiClient", return_value=mock):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    reg = er.async_get(hass)
    assert (
        reg.async_get_entity_id(
            "sensor", DOMAIN, f"site_{TEST_SITE_ID}_threat_heatmap_daily"
        )
        is not None
    )
    assert (
        reg.async_get_entity_id(
            "sensor", DOMAIN, f"site_{TEST_SITE_ID}_threat_heatmap_hourly"
        )
        is not None
    )
    assert len(entry.runtime_data.threat_heatmap_coordinators) == 4


async def test_threat_heatmap_sensors_skipped_when_disabled(
    hass: HomeAssistant,
) -> None:
    """No threat heatmap coordinators/sensors are created when toggle is False."""
    entry = _build_entry(
        hass,
        {CONF_ENABLE_THREAT_HEATMAP_SENSORS: False},
        "test_threat_heatmap_disabled",
    )
    mock = _build_mock_api([SAMPLE_DEVICE_AP])

    with patch("custom_components.omada_open_api.OmadaApiClient", return_value=mock):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    reg = er.async_get(hass)
    assert (
        reg.async_get_entity_id(
            "sensor", DOMAIN, f"site_{TEST_SITE_ID}_threat_heatmap_daily"
        )
        is None
    )
    assert entry.runtime_data.threat_heatmap_coordinators == []


async def test_client_signal_sensors_skipped_when_disabled(
    hass: HomeAssistant,
) -> None:
    """RSSI, SNR and signal strength sensors are not created when disabled.

    Regression test for the #111 beta report: CONF_ENABLE_CLIENT_SIGNAL_SENSORS
    was saved by the options flow but never read by the sensor platform.
    """
    client_mac = "11-22-33-44-55-AC"
    entry = _build_entry(
        hass,
        {
            CONF_ENABLE_CLIENT_SIGNAL_SENSORS: False,
            CONF_SELECTED_CLIENTS: [client_mac],
        },
        "test_toggle_client_signal",
    )
    mock = _build_mock_api([])
    mock.get_clients = AsyncMock(
        return_value={
            "data": [
                {
                    "mac": client_mac,
                    "name": "Phone",
                    "active": True,
                    "wireless": True,
                    "rssi": -60,
                    "snr": 30,
                    "signalLevel": 80,
                }
            ],
            "totalRows": 1,
            "currentPage": 1,
        }
    )

    with patch("custom_components.omada_open_api.OmadaApiClient", return_value=mock):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    reg = er.async_get(hass)
    for key in ("rssi", "snr", "signal_strength"):
        assert reg.async_get_entity_id("sensor", DOMAIN, f"{client_mac}_{key}") is None
    # Bandwidth sensors are governed by their own option and stay.
    assert (
        reg.async_get_entity_id("sensor", DOMAIN, f"{client_mac}_downloaded")
        is not None
    )


# ---------------------------------------------------------------------------
# GH #184: client count, radio utilization, client block and reconnect
# toggles. Each option set to False must keep its entities from being
# created; set to True (or left unset) the entities exist.
# ---------------------------------------------------------------------------

_AP_MAC = SAMPLE_DEVICE_AP["mac"]
_CLIENT_COUNT_UIDS = (
    f"{_AP_MAC}_client_num",
    f"{_AP_MAC}_wireless_clients",
    f"{_AP_MAC}_clients_2g",
    f"{_AP_MAC}_clients_5g",
)
_RADIO_UTIL_UIDS = (
    f"{_AP_MAC}_radio_tx_util_2g",
    f"{_AP_MAC}_radio_rx_util_2g",
    f"{_AP_MAC}_radio_inter_util_2g",
    f"{_AP_MAC}_radio_busy_util_5g",
)


def _build_ap_api() -> AsyncMock:
    """Mock an AP that reports per-band client counts and radio utilization."""
    mock = _build_mock_api([SAMPLE_DEVICE_AP])
    mock.get_device_client_stats = AsyncMock(
        return_value=[
            {"mac": _AP_MAC, "clientNum": 12, "clientNum2g": 5, "clientNum5g": 7}
        ]
    )
    band = {"actualChannel": "36", "txUtil": 10, "rxUtil": 20, "interUtil": 5}
    mock.get_ap_radios = AsyncMock(
        return_value={
            "wp2g": {**band, "busyUtil": 35},
            "wp5g": {**band, "busyUtil": 40},
        }
    )
    return mock


async def _setup_with(hass: HomeAssistant, entry: MockConfigEntry, mock) -> None:
    with patch("custom_components.omada_open_api.OmadaApiClient", return_value=mock):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


def _sensor_exists(hass: HomeAssistant, unique_id: str) -> bool:
    return (
        er.async_get(hass).async_get_entity_id("sensor", DOMAIN, unique_id) is not None
    )


@pytest.mark.parametrize("enabled", [True, False])
async def test_device_client_count_sensors_follow_option(
    hass: HomeAssistant, enabled: bool
) -> None:
    """Per-device and per-band client count sensors follow their option."""
    entry = _build_entry(
        hass,
        {CONF_ENABLE_DEVICE_CLIENT_COUNT_SENSORS: enabled},
        f"test_toggle_client_count_{enabled}",
    )
    await _setup_with(hass, entry, _build_ap_api())

    for unique_id in _CLIENT_COUNT_UIDS:
        assert _sensor_exists(hass, unique_id) is enabled, unique_id
    # Sensors of other categories are not affected.
    assert _sensor_exists(hass, f"{_AP_MAC}_cpu_util")
    assert _sensor_exists(hass, f"{_AP_MAC}_radio_tx_util_2g")


@pytest.mark.parametrize("enabled", [True, False])
async def test_device_radio_utilization_sensors_follow_option(
    hass: HomeAssistant, enabled: bool
) -> None:
    """Per-band radio utilization sensors follow their option."""
    entry = _build_entry(
        hass,
        {CONF_ENABLE_DEVICE_RADIO_UTILIZATION_SENSORS: enabled},
        f"test_toggle_radio_util_{enabled}",
    )
    await _setup_with(hass, entry, _build_ap_api())

    for unique_id in _RADIO_UTIL_UIDS:
        assert _sensor_exists(hass, unique_id) is enabled, unique_id
    assert _sensor_exists(hass, f"{_AP_MAC}_clients_2g")


async def test_radio_utilization_not_polled_when_disabled(
    hass: HomeAssistant,
) -> None:
    """With the option off, the coordinator skips the radio utilization poll."""
    entry = _build_entry(
        hass,
        {CONF_ENABLE_DEVICE_RADIO_UTILIZATION_SENSORS: False},
        "test_toggle_radio_util_poll",
    )
    mock = _build_ap_api()
    await _setup_with(hass, entry, mock)

    coordinator = entry.runtime_data.coordinators[TEST_SITE_ID]
    ap_data = coordinator.data["devices"][_AP_MAC]
    assert not any(key.startswith("radio_") for key in ap_data)


async def test_radio_utilization_polled_by_default(hass: HomeAssistant) -> None:
    """Without the option set, radio utilization is polled as before."""
    entry = _build_entry(hass, {}, "test_toggle_radio_util_default")
    await _setup_with(hass, entry, _build_ap_api())

    coordinator = entry.runtime_data.coordinators[TEST_SITE_ID]
    ap_data = coordinator.data["devices"][_AP_MAC]
    assert ap_data["radio_tx_util_2g"] == 10
    assert ap_data["radio_busy_util_5g"] == 40


def _build_client_api(client_mac: str) -> AsyncMock:
    mock = _build_mock_api([])
    mock.get_clients = AsyncMock(
        return_value={
            "data": [
                {
                    "mac": client_mac,
                    "name": "Phone",
                    "active": True,
                    "wireless": True,
                }
            ],
            "totalRows": 1,
            "currentPage": 1,
        }
    )
    return mock


@pytest.mark.parametrize("enabled", [True, False])
async def test_client_block_switch_follows_option(
    hass: HomeAssistant, enabled: bool
) -> None:
    """The per-client network access switch follows its option."""
    client_mac = "11-22-33-44-55-B1"
    entry = _build_entry(
        hass,
        {CONF_ENABLE_CLIENT_BLOCK_SWITCH: enabled, CONF_SELECTED_CLIENTS: [client_mac]},
        f"test_toggle_block_{enabled}",
    )
    await _setup_with(hass, entry, _build_client_api(client_mac))

    reg = er.async_get(hass)
    block_switch = reg.async_get_entity_id(
        "switch", DOMAIN, f"{DOMAIN}_{client_mac}_block"
    )
    assert (block_switch is not None) is enabled
    # The reconnect button has its own option and stays.
    assert (
        reg.async_get_entity_id("button", DOMAIN, f"{DOMAIN}_{client_mac}_reconnect")
        is not None
    )


@pytest.mark.parametrize("enabled", [True, False])
async def test_client_reconnect_button_follows_option(
    hass: HomeAssistant, enabled: bool
) -> None:
    """The per-client reconnect button follows its option."""
    client_mac = "11-22-33-44-55-B2"
    entry = _build_entry(
        hass,
        {
            CONF_ENABLE_CLIENT_RECONNECT_BUTTON: enabled,
            CONF_SELECTED_CLIENTS: [client_mac],
        },
        f"test_toggle_reconnect_{enabled}",
    )
    await _setup_with(hass, entry, _build_client_api(client_mac))

    reg = er.async_get(hass)
    button = reg.async_get_entity_id(
        "button", DOMAIN, f"{DOMAIN}_{client_mac}_reconnect"
    )
    assert (button is not None) is enabled
    assert (
        reg.async_get_entity_id("switch", DOMAIN, f"{DOMAIN}_{client_mac}_block")
        is not None
    )


# ---------------------------------------------------------------------------
# GH #184: the sensor key categories behind the device options.
# ---------------------------------------------------------------------------

_DIAGNOSTIC_KEYS = {
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
_CLIENT_COUNT_KEYS = {
    "client_num",
    "wired_clients",
    "wireless_clients",
    "guest_clients",
    "clients_2g",
    "clients_5g",
    "clients_5g2",
    "clients_6g",
}
_RADIO_UTIL_KEYS = {
    f"radio_{kind}_util_{band}"
    for kind in ("tx", "rx", "inter", "busy")
    for band in ("2g", "5g", "5g2", "6g")
}


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({}, set()),
        ({CONF_ENABLE_DEVICE_DIAGNOSTIC_SENSORS: False}, _DIAGNOSTIC_KEYS),
        ({CONF_ENABLE_DEVICE_CLIENT_COUNT_SENSORS: False}, _CLIENT_COUNT_KEYS),
        ({CONF_ENABLE_DEVICE_RADIO_UTILIZATION_SENSORS: False}, _RADIO_UTIL_KEYS),
        (
            {
                CONF_ENABLE_DEVICE_DIAGNOSTIC_SENSORS: False,
                CONF_ENABLE_DEVICE_CLIENT_COUNT_SENSORS: False,
                CONF_ENABLE_DEVICE_RADIO_UTILIZATION_SENSORS: False,
            },
            _DIAGNOSTIC_KEYS | _CLIENT_COUNT_KEYS | _RADIO_UTIL_KEYS,
        ),
    ],
)
def test_excluded_device_sensor_keys(options: dict, expected: set[str]) -> None:
    """Each turned-off category excludes exactly its sensor keys."""
    assert _excluded_device_sensor_keys(options) == expected


def test_band_entities_skip_excluded_keys_only_once_created() -> None:
    """Excluded band sensors are skipped; the others are created once."""
    coordinator = MagicMock()
    # A device without a type comes first: it must not end the scan.
    devices = {
        "AA-BB-CC-DD-EE-77": {"name": "no type"},
        _AP_MAC: {
            "type": "ap",
            "client_num_2g": 1,
            "client_num_5g": 2,
            "radio_tx_util_2g": 3,
            "radio_rx_util_2g": 4,
        },
    }
    known: set[tuple[str, str]] = set()
    excluded = frozenset({"clients_2g", "radio_tx_util_2g"})

    with patch(
        "custom_components.omada_open_api.sensor._make_device_sensor",
        side_effect=lambda _coord, desc, mac: (mac, desc.key),
    ):
        created = _check_ap_band_entities(coordinator, devices, known, excluded)
        again = _check_ap_band_entities(coordinator, devices, known, excluded)

    assert sorted(created) == [
        (_AP_MAC, "clients_5g"),
        (_AP_MAC, "radio_rx_util_2g"),
    ]
    assert again == []


async def test_site_coordinator_polls_radio_utilization_by_default(
    hass: HomeAssistant,
) -> None:
    """A coordinator built without the flag still polls radio utilization."""
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=_build_ap_api(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    data = await coordinator._async_update_data()

    assert data["devices"][_AP_MAC]["radio_tx_util_2g"] == 10
