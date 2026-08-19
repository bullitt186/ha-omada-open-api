"""Tests for AP_BAND_RADIO_UTIL_SENSORS entity descriptions — TDD Cycle 2."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from homeassistant.components.sensor import SensorStateClass
from homeassistant.const import PERCENTAGE, EntityCategory

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.omada_open_api.coordinator import OmadaSiteCoordinator
from custom_components.omada_open_api.devices import process_device
from custom_components.omada_open_api.sensor import (
    AP_BAND_RADIO_UTIL_SENSORS,
    OmadaDeviceSensor,
)

from .conftest import SAMPLE_DEVICE_AP, TEST_SITE_ID, TEST_SITE_NAME

AP_MAC = "AA-BB-CC-DD-EE-01"

_RADIO_UTIL_KEYS = [
    "radio_tx_util_2g",
    "radio_rx_util_2g",
    "radio_inter_util_2g",
    "radio_busy_util_2g",
    "radio_tx_util_5g",
    "radio_rx_util_5g",
    "radio_inter_util_5g",
    "radio_busy_util_5g",
    "radio_tx_util_5g2",
    "radio_rx_util_5g2",
    "radio_inter_util_5g2",
    "radio_busy_util_5g2",
    "radio_tx_util_6g",
    "radio_rx_util_6g",
    "radio_inter_util_6g",
    "radio_busy_util_6g",
]


def _make_sensor(
    hass: HomeAssistant, device_data: dict, description_key: str
) -> OmadaDeviceSensor:
    """Create an OmadaDeviceSensor for the given radio util description key."""
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    coordinator.data = {
        "devices": {AP_MAC: device_data},
        "poe_ports": {},
        "poe_budget": {},
        "site_id": TEST_SITE_ID,
        "site_name": TEST_SITE_NAME,
    }
    description = next(
        d for d in AP_BAND_RADIO_UTIL_SENSORS if d.key == description_key
    )
    return OmadaDeviceSensor(
        coordinator=coordinator,
        description=description,
        device_mac=AP_MAC,
    )


def _full_radio_data() -> dict:
    """Return AP device data with all radio utilization keys populated."""
    data = process_device(SAMPLE_DEVICE_AP)
    data.update(
        {
            "radio_tx_util_2g": 45,
            "radio_rx_util_2g": 30,
            "radio_inter_util_2g": 10,
            "radio_busy_util_2g": 55,
            "radio_tx_util_5g": 20,
            "radio_rx_util_5g": 15,
            "radio_inter_util_5g": 5,
            "radio_busy_util_5g": 25,
            "radio_tx_util_5g2": 0,
            "radio_rx_util_5g2": 0,
            "radio_inter_util_5g2": 0,
            "radio_busy_util_5g2": 0,
            "radio_tx_util_6g": 10,
            "radio_rx_util_6g": 8,
            "radio_inter_util_6g": 2,
            "radio_busy_util_6g": None,
        }
    )
    return data


# ---------------------------------------------------------------------------
# Tuple structure
# ---------------------------------------------------------------------------


def test_tuple_has_16_entries() -> None:
    """Test that AP_BAND_RADIO_UTIL_SENSORS contains exactly 16 descriptions."""
    assert len(AP_BAND_RADIO_UTIL_SENSORS) == 16


def test_all_expected_keys_present() -> None:
    """Test that all 16 expected sensor keys are present in the tuple."""
    actual_keys = {d.key for d in AP_BAND_RADIO_UTIL_SENSORS}
    assert actual_keys == set(_RADIO_UTIL_KEYS)


def test_all_have_diagnostic_entity_category() -> None:
    """Test that every description uses EntityCategory.DIAGNOSTIC."""
    for desc in AP_BAND_RADIO_UTIL_SENSORS:
        assert desc.entity_category == EntityCategory.DIAGNOSTIC, (
            f"{desc.key} missing DIAGNOSTIC category"
        )


def test_all_have_percentage_unit() -> None:
    """Test that every description uses PERCENTAGE as unit of measurement."""
    for desc in AP_BAND_RADIO_UTIL_SENSORS:
        assert desc.native_unit_of_measurement == PERCENTAGE, (
            f"{desc.key} missing PERCENTAGE unit"
        )


def test_all_have_measurement_state_class() -> None:
    """Test that every description uses SensorStateClass.MEASUREMENT."""
    for desc in AP_BAND_RADIO_UTIL_SENSORS:
        assert desc.state_class == SensorStateClass.MEASUREMENT, (
            f"{desc.key} missing MEASUREMENT state class"
        )


def test_all_disabled_by_default() -> None:
    """Test that every sensor is disabled in the entity registry by default."""
    for desc in AP_BAND_RADIO_UTIL_SENSORS:
        assert desc.entity_registry_enabled_default is False, (
            f"{desc.key} should be disabled by default"
        )


# ---------------------------------------------------------------------------
# value_fn correctness
# ---------------------------------------------------------------------------


async def test_tx_util_2g_value(hass: HomeAssistant) -> None:
    """Test 2.4 GHz TX utilization sensor returns correct value."""
    sensor = _make_sensor(hass, _full_radio_data(), "radio_tx_util_2g")
    assert sensor.native_value == 45


async def test_rx_util_2g_value(hass: HomeAssistant) -> None:
    """Test 2.4 GHz RX utilization sensor returns correct value."""
    sensor = _make_sensor(hass, _full_radio_data(), "radio_rx_util_2g")
    assert sensor.native_value == 30


async def test_inter_util_2g_value(hass: HomeAssistant) -> None:
    """Test 2.4 GHz interference sensor returns correct value."""
    sensor = _make_sensor(hass, _full_radio_data(), "radio_inter_util_2g")
    assert sensor.native_value == 10


async def test_busy_util_2g_value(hass: HomeAssistant) -> None:
    """Test 2.4 GHz channel-busy sensor returns correct value."""
    sensor = _make_sensor(hass, _full_radio_data(), "radio_busy_util_2g")
    assert sensor.native_value == 55


async def test_tx_util_5g_value(hass: HomeAssistant) -> None:
    """Test 5 GHz-1 TX utilization sensor returns correct value."""
    sensor = _make_sensor(hass, _full_radio_data(), "radio_tx_util_5g")
    assert sensor.native_value == 20


async def test_tx_util_5g2_value(hass: HomeAssistant) -> None:
    """Test 5 GHz-2 TX utilization sensor returns 0 (not unavailable)."""
    sensor = _make_sensor(hass, _full_radio_data(), "radio_tx_util_5g2")
    assert sensor.native_value == 0
    assert sensor.available is True


async def test_tx_util_6g_value(hass: HomeAssistant) -> None:
    """Test 6 GHz TX utilization sensor returns correct value."""
    sensor = _make_sensor(hass, _full_radio_data(), "radio_tx_util_6g")
    assert sensor.native_value == 10


# ---------------------------------------------------------------------------
# available_fn — absent key means unavailable
# ---------------------------------------------------------------------------


async def test_sensor_unavailable_when_key_absent(hass: HomeAssistant) -> None:
    """Test sensor is unavailable when the radio util key is not in device data."""
    data = process_device(SAMPLE_DEVICE_AP)
    # No radio util keys merged yet
    sensor = _make_sensor(hass, data, "radio_tx_util_2g")
    assert sensor.available is False


async def test_sensor_available_when_value_is_zero(hass: HomeAssistant) -> None:
    """Test sensor is available even when the value is 0 (zero ≠ absent)."""
    data = process_device(SAMPLE_DEVICE_AP)
    data["radio_tx_util_5g2"] = 0
    sensor = _make_sensor(hass, data, "radio_tx_util_5g2")
    assert sensor.available is True
    assert sensor.native_value == 0


async def test_busy_util_unavailable_when_none_non_mtk(hass: HomeAssistant) -> None:
    """Test busyUtil sensor is unavailable when value is None (non-MTK device)."""
    data = process_device(SAMPLE_DEVICE_AP)
    data["radio_busy_util_2g"] = None
    sensor = _make_sensor(hass, data, "radio_busy_util_2g")
    assert sensor.available is False


async def test_sensor_unavailable_when_5g2_not_in_response(hass: HomeAssistant) -> None:
    """Test 5 GHz-2 sensor unavailable when AP has no second 5 GHz radio."""
    data = process_device(SAMPLE_DEVICE_AP)
    # Only 2.4 and 5 GHz-1 present, not 5g2
    data["radio_tx_util_2g"] = 30
    data["radio_tx_util_5g"] = 10
    sensor = _make_sensor(hass, data, "radio_tx_util_5g2")
    assert sensor.available is False


# ---------------------------------------------------------------------------
# Coordinator failure makes all sensors unavailable
# ---------------------------------------------------------------------------


async def test_sensor_unavailable_on_coordinator_failure(hass: HomeAssistant) -> None:
    """Test sensor unavailable when coordinator last update failed."""
    sensor = _make_sensor(hass, _full_radio_data(), "radio_tx_util_2g")
    sensor.coordinator.last_update_success = False
    assert sensor.available is False
