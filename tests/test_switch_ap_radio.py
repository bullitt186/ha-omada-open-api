"""Tests for AP radio on/off switches per band (Issue #5)."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
import pytest

from custom_components.omada_open_api.api import OmadaApiClient, OmadaApiError
from custom_components.omada_open_api.coordinator import OmadaSiteCoordinator
from custom_components.omada_open_api.switch import OmadaApRadioSwitch

from .conftest import (
    SAMPLE_DEVICE_AP,
    SAMPLE_DEVICE_SWITCH,
    TEST_SITE_ID,
    TEST_SITE_NAME,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

AP_MAC = "AA-BB-CC-DD-EE-01"

# Sample radio config from the API
SAMPLE_RADIO_CONFIG_DUAL = {
    "radioSetting2g": {"radioEnable": True},
    "radioSetting5g": {"radioEnable": False},
}

SAMPLE_RADIO_CONFIG_QUAD = {
    "radioSetting2g": {"radioEnable": True},
    "radioSetting5g": {"radioEnable": True},
    "radioSetting5g2": {"radioEnable": False},
    "radioSetting6g": {"radioEnable": True},
}


def _make_coordinator(
    hass: HomeAssistant,
    ap_radio_config: dict | None = None,
) -> OmadaSiteCoordinator:
    """Build coordinator with ap_radio_config data."""
    coord = OmadaSiteCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    coord.data = {
        "devices": {
            AP_MAC: {
                "mac": AP_MAC,
                "name": "Office AP",
                "type": "ap",
                "status": 1,
            }
        },
        "ap_radio_config": ap_radio_config or {},
        "site_id": TEST_SITE_ID,
        "site_name": TEST_SITE_NAME,
    }
    return coord


# ---------------------------------------------------------------------------
# OmadaApRadioSwitch — state
# ---------------------------------------------------------------------------


async def test_radio_switch_is_on_when_enabled(hass: HomeAssistant) -> None:
    """Switch is on when radioEnable is True."""
    coord = _make_coordinator(hass, ap_radio_config={AP_MAC: SAMPLE_RADIO_CONFIG_DUAL})
    switch = OmadaApRadioSwitch(
        coordinator=coord,
        ap_mac=AP_MAC,
        band="2g",
        radio_setting_key="radioSetting2g",
    )
    assert switch.is_on is True


async def test_radio_switch_is_off_when_disabled(hass: HomeAssistant) -> None:
    """Switch is off when radioEnable is False."""
    coord = _make_coordinator(hass, ap_radio_config={AP_MAC: SAMPLE_RADIO_CONFIG_DUAL})
    switch = OmadaApRadioSwitch(
        coordinator=coord,
        ap_mac=AP_MAC,
        band="5g",
        radio_setting_key="radioSetting5g",
    )
    assert switch.is_on is False


async def test_radio_switch_unique_id(hass: HomeAssistant) -> None:
    """Switch unique_id encodes AP MAC and band."""
    coord = _make_coordinator(hass, ap_radio_config={AP_MAC: SAMPLE_RADIO_CONFIG_DUAL})
    switch = OmadaApRadioSwitch(
        coordinator=coord,
        ap_mac=AP_MAC,
        band="2g",
        radio_setting_key="radioSetting2g",
    )
    assert switch.unique_id == f"{AP_MAC}_radio_2g"


async def test_radio_switch_entity_category_config(hass: HomeAssistant) -> None:
    """Switch has EntityCategory.CONFIG."""
    coord = _make_coordinator(hass, ap_radio_config={AP_MAC: SAMPLE_RADIO_CONFIG_DUAL})
    switch = OmadaApRadioSwitch(
        coordinator=coord,
        ap_mac=AP_MAC,
        band="2g",
        radio_setting_key="radioSetting2g",
    )
    assert switch.entity_category == EntityCategory.CONFIG


async def test_radio_switch_unavailable_when_no_config(hass: HomeAssistant) -> None:
    """Switch is unavailable when AP has no radio config data."""
    coord = _make_coordinator(hass, ap_radio_config={})
    switch = OmadaApRadioSwitch(
        coordinator=coord,
        ap_mac=AP_MAC,
        band="2g",
        radio_setting_key="radioSetting2g",
    )
    assert switch.available is False


async def test_radio_switch_unavailable_on_coordinator_failure(
    hass: HomeAssistant,
) -> None:
    """Switch is unavailable when coordinator update fails."""
    coord = _make_coordinator(hass, ap_radio_config={AP_MAC: SAMPLE_RADIO_CONFIG_DUAL})
    coord.last_update_success = False
    switch = OmadaApRadioSwitch(
        coordinator=coord,
        ap_mac=AP_MAC,
        band="2g",
        radio_setting_key="radioSetting2g",
    )
    assert switch.available is False


async def test_radio_switch_available_when_data_present(hass: HomeAssistant) -> None:
    """Switch is available when radio config data is present."""
    coord = _make_coordinator(hass, ap_radio_config={AP_MAC: SAMPLE_RADIO_CONFIG_DUAL})
    switch = OmadaApRadioSwitch(
        coordinator=coord,
        ap_mac=AP_MAC,
        band="2g",
        radio_setting_key="radioSetting2g",
    )
    assert switch.available is True


# ---------------------------------------------------------------------------
# OmadaApRadioSwitch — turn_on / turn_off
# ---------------------------------------------------------------------------


async def test_radio_switch_turn_on_calls_api(hass: HomeAssistant) -> None:
    """turn_on calls set_ap_radio_enabled(enabled=True) and requests refresh."""
    mock_api = MagicMock()
    mock_api.set_ap_radio_enabled = AsyncMock()
    mock_api.api_url = "https://api.example.com"

    coord = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    coord.data = {
        "devices": {AP_MAC: {"mac": AP_MAC, "name": "Office AP", "type": "ap"}},
        "ap_radio_config": {AP_MAC: SAMPLE_RADIO_CONFIG_DUAL},
        "site_id": TEST_SITE_ID,
        "site_name": TEST_SITE_NAME,
    }

    switch = OmadaApRadioSwitch(
        coordinator=coord,
        ap_mac=AP_MAC,
        band="5g",
        radio_setting_key="radioSetting5g",
    )

    with patch.object(
        coord, "async_request_refresh", new_callable=AsyncMock
    ) as mock_refresh:
        await switch.async_turn_on()

    mock_api.set_ap_radio_enabled.assert_called_once_with(
        TEST_SITE_ID, AP_MAC, band="5g", enabled=True
    )
    mock_refresh.assert_called_once()


async def test_radio_switch_turn_off_calls_api(hass: HomeAssistant) -> None:
    """turn_off calls set_ap_radio_enabled(enabled=False) and requests refresh."""
    mock_api = MagicMock()
    mock_api.set_ap_radio_enabled = AsyncMock()
    mock_api.api_url = "https://api.example.com"

    coord = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    coord.data = {
        "devices": {AP_MAC: {"mac": AP_MAC, "name": "Office AP", "type": "ap"}},
        "ap_radio_config": {AP_MAC: SAMPLE_RADIO_CONFIG_DUAL},
        "site_id": TEST_SITE_ID,
        "site_name": TEST_SITE_NAME,
    }

    switch = OmadaApRadioSwitch(
        coordinator=coord,
        ap_mac=AP_MAC,
        band="2g",
        radio_setting_key="radioSetting2g",
    )

    with patch.object(
        coord, "async_request_refresh", new_callable=AsyncMock
    ) as mock_refresh:
        await switch.async_turn_off()

    mock_api.set_ap_radio_enabled.assert_called_once_with(
        TEST_SITE_ID, AP_MAC, band="2g", enabled=False
    )
    mock_refresh.assert_called_once()


async def test_radio_switch_turn_on_raises_on_api_error(hass: HomeAssistant) -> None:
    """turn_on raises HomeAssistantError when API call fails."""
    mock_api = MagicMock()
    mock_api.set_ap_radio_enabled = AsyncMock(
        side_effect=OmadaApiError("Radio control failed")
    )
    mock_api.api_url = "https://api.example.com"

    coord = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    coord.data = {
        "devices": {AP_MAC: {"mac": AP_MAC, "name": "Office AP", "type": "ap"}},
        "ap_radio_config": {AP_MAC: SAMPLE_RADIO_CONFIG_DUAL},
        "site_id": TEST_SITE_ID,
        "site_name": TEST_SITE_NAME,
    }

    switch = OmadaApRadioSwitch(
        coordinator=coord,
        ap_mac=AP_MAC,
        band="2g",
        radio_setting_key="radioSetting2g",
    )

    with pytest.raises(HomeAssistantError):
        await switch.async_turn_on()


# ---------------------------------------------------------------------------
# API: get_ap_radio_config and set_ap_radio_enabled
# ---------------------------------------------------------------------------


async def test_api_get_ap_radio_config_calls_correct_url() -> None:
    """get_ap_radio_config calls the radio-config GET endpoint."""
    expected_result = SAMPLE_RADIO_CONFIG_DUAL

    with patch.object(
        OmadaApiClient,
        "_authenticated_request",
        new_callable=AsyncMock,
        return_value={"errorCode": 0, "result": expected_result},
    ) as mock_req:
        real_client = OmadaApiClient(
            session=MagicMock(),
            token_update_callback=AsyncMock(),
            api_url="https://api.example.com",
            omada_id="test_omada_id",
            client_id="cid",
            client_secret="csec",
            access_token="tok",
            refresh_token="rtok",
            token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
        )
        result = await real_client.get_ap_radio_config(TEST_SITE_ID, AP_MAC)

    assert result == expected_result
    mock_req.assert_called_once()
    call_url = mock_req.call_args[0][1]
    assert "radio-config" in call_url
    assert AP_MAC in call_url
    assert TEST_SITE_ID in call_url


async def test_api_set_ap_radio_enabled_patches_correct_band() -> None:
    """set_ap_radio_enabled sends PATCH with the correct band key and value."""
    with patch.object(
        OmadaApiClient,
        "_authenticated_request",
        new_callable=AsyncMock,
        return_value={"errorCode": 0, "result": {}},
    ) as mock_req:
        real_client = OmadaApiClient(
            session=MagicMock(),
            token_update_callback=AsyncMock(),
            api_url="https://api.example.com",
            omada_id="test_omada_id",
            client_id="cid",
            client_secret="csec",
            access_token="tok",
            refresh_token="rtok",
            token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
        )
        await real_client.set_ap_radio_enabled(
            TEST_SITE_ID, AP_MAC, band="2g", enabled=False
        )

    mock_req.assert_called_once()
    call_args = mock_req.call_args
    assert call_args.args[0] == "patch"
    assert "radio-config" in call_args.args[1]
    payload = call_args.kwargs.get("json_data")
    assert payload is not None
    assert "radioSetting2g" in payload
    assert payload["radioSetting2g"]["radioEnable"] is False


# ---------------------------------------------------------------------------
# Coordinator: ap_radio_config is fetched and stored
# ---------------------------------------------------------------------------


def _build_minimal_mock_api() -> MagicMock:
    """Build a minimal mock API for coordinator update tests."""
    mock_api = MagicMock()
    mock_api.api_url = "https://api.example.com"
    mock_api.get_devices = AsyncMock(return_value=[])
    mock_api.get_device_uplink_info = AsyncMock(return_value=[])
    mock_api.get_device_client_stats = AsyncMock(return_value=[])
    mock_api.get_ap_radios = AsyncMock(return_value={})
    mock_api.get_gateway_info = AsyncMock(return_value={})
    mock_api.get_site_ssids_comprehensive = AsyncMock(return_value=[])
    mock_api.get_ap_ssid_overrides = AsyncMock(return_value={"ssidOverrides": []})
    mock_api.get_poe_usage = AsyncMock(return_value=[])
    mock_api.get_switch_ports_poe = AsyncMock(return_value=[])
    mock_api.get_clients = AsyncMock(
        return_value={"data": [], "totalRows": 0, "currentPage": 1}
    )
    mock_api.get_gateway_wan_status = AsyncMock(return_value=[])
    mock_api.get_gateway_wan_speed_test_result = AsyncMock(return_value={})
    mock_api.get_vpn_s2s_stats = AsyncMock(return_value=[])
    mock_api.get_vpn_server_stats = AsyncMock(return_value=[])
    mock_api.get_vpn_client_stats = AsyncMock(return_value=[])
    mock_api.get_firmware_info = AsyncMock(return_value={})
    mock_api.get_switch_port_details = AsyncMock(return_value=[])
    mock_api.get_wlan_optimization_status = AsyncMock(
        return_value={"status": 0, "beforeIndex": 55, "afterIndex": 80}
    )
    mock_api.get_ap_led_setting = AsyncMock(return_value={})
    return mock_api


async def test_coordinator_fetches_ap_radio_config_for_aps(
    hass: HomeAssistant,
) -> None:
    """Coordinator stores ap_radio_config keyed by AP MAC."""
    mock_api = _build_minimal_mock_api()
    mock_api.get_devices = AsyncMock(
        return_value=[SAMPLE_DEVICE_AP, SAMPLE_DEVICE_SWITCH]
    )
    mock_api.get_device_uplink_info = AsyncMock(return_value=[])
    mock_api.get_ap_radio_config = AsyncMock(return_value=SAMPLE_RADIO_CONFIG_DUAL)

    coord = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    data = await coord._async_update_data()

    assert "ap_radio_config" in data
    ap_mac = SAMPLE_DEVICE_AP["mac"]
    assert ap_mac in data["ap_radio_config"]
    assert data["ap_radio_config"][ap_mac] == SAMPLE_RADIO_CONFIG_DUAL
    # Switch should not have radio config
    sw_mac = SAMPLE_DEVICE_SWITCH["mac"]
    assert sw_mac not in data["ap_radio_config"]


async def test_coordinator_ap_radio_config_empty_on_api_error(
    hass: HomeAssistant,
) -> None:
    """ap_radio_config[ap_mac] is absent when the API call fails for an AP."""
    mock_api = _build_minimal_mock_api()
    mock_api.get_devices = AsyncMock(return_value=[SAMPLE_DEVICE_AP])
    mock_api.get_device_uplink_info = AsyncMock(return_value=[])
    mock_api.get_ap_radio_config = AsyncMock(
        side_effect=OmadaApiError("Radio config unavailable")
    )

    coord = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    data = await coord._async_update_data()

    assert data["ap_radio_config"] == {}


# ---------------------------------------------------------------------------
# Coordinator: AP led_setting is fetched and merged into devices dict
# ---------------------------------------------------------------------------


async def test_coordinator_fetches_led_setting_for_aps(
    hass: HomeAssistant,
) -> None:
    """Coordinator merges led_setting into each AP device's data."""
    mock_api = _build_minimal_mock_api()
    mock_api.get_devices = AsyncMock(
        return_value=[SAMPLE_DEVICE_AP, SAMPLE_DEVICE_SWITCH]
    )
    mock_api.get_device_uplink_info = AsyncMock(return_value=[])
    mock_api.get_ap_radio_config = AsyncMock(return_value={})
    mock_api.get_ap_led_setting = AsyncMock(return_value={"ledSetting": 1})

    coord = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    data = await coord._async_update_data()

    ap_mac = SAMPLE_DEVICE_AP["mac"]
    assert data["devices"][ap_mac]["led_setting"] == 1
    # Switch device should not have a live led_setting merged in.
    sw_mac = SAMPLE_DEVICE_SWITCH["mac"]
    assert data["devices"][sw_mac]["led_setting"] is None


async def test_coordinator_led_setting_absent_on_api_error(
    hass: HomeAssistant,
) -> None:
    """led_setting is absent from AP device data when the API call fails."""
    mock_api = _build_minimal_mock_api()
    mock_api.get_devices = AsyncMock(return_value=[SAMPLE_DEVICE_AP])
    mock_api.get_device_uplink_info = AsyncMock(return_value=[])
    mock_api.get_ap_radio_config = AsyncMock(return_value={})
    mock_api.get_ap_led_setting = AsyncMock(
        side_effect=OmadaApiError("LED setting unavailable")
    )

    coord = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    data = await coord._async_update_data()

    ap_mac = SAMPLE_DEVICE_AP["mac"]
    assert data["devices"][ap_mac]["led_setting"] is None
