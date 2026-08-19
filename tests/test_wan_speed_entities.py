"""Tests for WAN speed test coordinator, sensors, and button."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.omada_open_api.button import OmadaWanSpeedTestButton
from custom_components.omada_open_api.const import DOMAIN
from custom_components.omada_open_api.sensor import (
    WAN_SPEED_SENSORS,
    OmadaWanSpeedSensor,
)

from .conftest import TEST_SITE_ID, TEST_SITE_NAME

GW_MAC = "AA-BB-CC-DD-EE-03"

SAMPLE_SPEED_TEST_RESULT = {
    "id": 1,
    "downloadSpeed": 100.5,
    "uploadSpeed": 50.2,
    "latency": 15,
    "testTime": 1692000000000,
    "status": 1,
}


def _build_coordinator_data(speed_test: dict | None = None) -> dict:
    return {
        "devices": {GW_MAC: {"type": "gateway", "name": "Main Gateway"}},
        "wan_speed_test": speed_test or {},
        "site_id": TEST_SITE_ID,
        "site_name": TEST_SITE_NAME,
    }


def _make_coordinator(hass, data):
    from custom_components.omada_open_api.coordinator import OmadaSiteCoordinator

    coord = OmadaSiteCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    coord.data = data
    return coord


# --- Sensor description tests ---


def test_wan_speed_sensor_keys() -> None:
    keys = {d.key for d in WAN_SPEED_SENSORS}
    assert "wan_speed_download" in keys
    assert "wan_speed_upload" in keys
    assert "wan_speed_latency" in keys
    assert "wan_speed_last_test" in keys


def test_wan_speed_download_value() -> None:
    desc = next(d for d in WAN_SPEED_SENSORS if d.key == "wan_speed_download")
    assert desc.value_fn(SAMPLE_SPEED_TEST_RESULT) == 100.5


def test_wan_speed_upload_value() -> None:
    desc = next(d for d in WAN_SPEED_SENSORS if d.key == "wan_speed_upload")
    assert desc.value_fn(SAMPLE_SPEED_TEST_RESULT) == 50.2


def test_wan_speed_latency_value() -> None:
    desc = next(d for d in WAN_SPEED_SENSORS if d.key == "wan_speed_latency")
    assert desc.value_fn(SAMPLE_SPEED_TEST_RESULT) == 15


def test_wan_speed_last_test_value() -> None:
    desc = next(d for d in WAN_SPEED_SENSORS if d.key == "wan_speed_last_test")
    assert desc.value_fn(SAMPLE_SPEED_TEST_RESULT) == 1692000000000


# --- Entity tests ---


async def test_wan_speed_sensor_native_value(hass: HomeAssistant) -> None:
    data = _build_coordinator_data(speed_test=SAMPLE_SPEED_TEST_RESULT)
    coord = _make_coordinator(hass, data)
    desc = next(d for d in WAN_SPEED_SENSORS if d.key == "wan_speed_download")
    sensor = OmadaWanSpeedSensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
    )
    assert sensor.native_value == 100.5


async def test_wan_speed_sensor_unavailable_without_data(hass: HomeAssistant) -> None:
    data = _build_coordinator_data(speed_test={})
    coord = _make_coordinator(hass, data)
    desc = next(d for d in WAN_SPEED_SENSORS if d.key == "wan_speed_download")
    sensor = OmadaWanSpeedSensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
    )
    assert sensor.available is False


def test_wan_speed_sensor_unique_id() -> None:
    coord = MagicMock()
    coord.data = _build_coordinator_data(speed_test=SAMPLE_SPEED_TEST_RESULT)
    desc = next(d for d in WAN_SPEED_SENSORS if d.key == "wan_speed_download")
    sensor = OmadaWanSpeedSensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
    )
    assert sensor.unique_id == f"{GW_MAC}_wan_speed_download"


def test_wan_speed_sensor_device_info() -> None:
    coord = MagicMock()
    coord.data = _build_coordinator_data(speed_test=SAMPLE_SPEED_TEST_RESULT)
    desc = next(d for d in WAN_SPEED_SENSORS if d.key == "wan_speed_download")
    sensor = OmadaWanSpeedSensor(
        coordinator=coord,
        description=desc,
        gateway_mac=GW_MAC,
    )
    assert (DOMAIN, GW_MAC) in sensor.device_info["identifiers"]


# --- Button tests ---


def test_wan_speed_test_button_unique_id() -> None:
    coord = MagicMock()
    coord.site_id = TEST_SITE_ID
    coord.site_name = TEST_SITE_NAME
    coord.data = _build_coordinator_data()
    button = OmadaWanSpeedTestButton(coordinator=coord, gateway_mac=GW_MAC)
    assert button.unique_id == f"{GW_MAC}_wan_speed_test_trigger"


def test_wan_speed_test_button_translation_key() -> None:
    coord = MagicMock()
    coord.site_id = TEST_SITE_ID
    coord.site_name = TEST_SITE_NAME
    coord.data = _build_coordinator_data()
    button = OmadaWanSpeedTestButton(coordinator=coord, gateway_mac=GW_MAC)
    assert button.translation_key == "wan_speed_test_trigger"


def test_wan_speed_test_button_device_info() -> None:
    coord = MagicMock()
    coord.site_id = TEST_SITE_ID
    coord.site_name = TEST_SITE_NAME
    coord.data = _build_coordinator_data()
    button = OmadaWanSpeedTestButton(coordinator=coord, gateway_mac=GW_MAC)
    assert (DOMAIN, GW_MAC) in button.device_info["identifiers"]


async def test_wan_speed_test_button_press(hass: HomeAssistant) -> None:
    coord = MagicMock()
    coord.site_id = TEST_SITE_ID
    coord.site_name = TEST_SITE_NAME
    coord.data = _build_coordinator_data()
    coord.api_client = AsyncMock()
    button = OmadaWanSpeedTestButton(coordinator=coord, gateway_mac=GW_MAC)
    await button.async_press()
    coord.api_client.trigger_wan_speed_test.assert_called_once_with(TEST_SITE_ID)
