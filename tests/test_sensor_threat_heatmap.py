"""Tests for OmadaThreatHeatmapSensor entity."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from homeassistant.components.sensor import SensorStateClass

from custom_components.omada_open_api.const import DOMAIN
from custom_components.omada_open_api.coordinator import OmadaThreatHeatmapCoordinator
from custom_components.omada_open_api.sensor import OmadaThreatHeatmapSensor

from .conftest import TEST_SITE_ID, TEST_SITE_NAME

SAMPLE_POINT = {
    "lat": 38.0,
    "lon": -97.0,
    "country": "US",
    "value": 435,
    "sample_ips": ["1.2.3.4"],
    "top_signatures": [["ET EXPLOIT Foo", 10]],
    "top_activities": [["Scan", 18]],
    "severities": {"1": 22, "4": 1},
    "latest_time": 1781943373,
}


def _build_heatmap_data(*, available: bool = True) -> dict:
    return {
        "source": "omada_open_api.security.threat-management",
        "site_id": TEST_SITE_ID,
        "site_name": TEST_SITE_NAME,
        "window": "monthly",
        "window_start": 1779397184,
        "window_end": 1781989184,
        "total_rows": 667,
        "fetched_rows": 667,
        "skipped_rows": 5,
        "max": 435,
        "points": [SAMPLE_POINT],
        "available": available,
    }


def _create_sensor(hass: HomeAssistant, data: dict) -> OmadaThreatHeatmapSensor:
    coordinator = OmadaThreatHeatmapCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        window="monthly",
    )
    coordinator.data = data
    return OmadaThreatHeatmapSensor(coordinator=coordinator)


async def test_native_value_is_raw_row_count(hass: HomeAssistant) -> None:
    """Sensor state equals the raw threat row count for the window."""
    sensor = _create_sensor(hass, _build_heatmap_data())
    assert sensor.native_value == 667


async def test_unique_id_includes_site_and_window(hass: HomeAssistant) -> None:
    """Unique ID is stable and includes site ID plus window."""
    sensor = _create_sensor(hass, _build_heatmap_data())
    assert sensor.unique_id == f"site_{TEST_SITE_ID}_threat_heatmap_monthly"


async def test_device_info_links_to_site_device(hass: HomeAssistant) -> None:
    """Sensor is attached to the site device."""
    sensor = _create_sensor(hass, _build_heatmap_data())
    assert sensor.device_info is not None
    assert sensor.device_info["identifiers"] == {(DOMAIN, f"site_{TEST_SITE_ID}")}


async def test_extra_state_attributes_match_contract(hass: HomeAssistant) -> None:
    """Attributes match the documented contract exactly."""
    sensor = _create_sensor(hass, _build_heatmap_data())
    attrs = sensor.extra_state_attributes
    assert attrs is not None
    for key in (
        "source",
        "site_id",
        "site_name",
        "window",
        "window_start",
        "window_end",
        "total_rows",
        "fetched_rows",
        "skipped_rows",
        "max",
        "points",
    ):
        assert key in attrs
    assert attrs["site_id"] == TEST_SITE_ID
    assert attrs["window"] == "monthly"
    assert attrs["max"] == 435
    assert attrs["points"][0]["country"] == "US"


async def test_state_class_and_unit(hass: HomeAssistant) -> None:
    """Sensor uses measurement state class and 'threats' unit."""
    sensor = _create_sensor(hass, _build_heatmap_data())
    assert sensor.entity_description.state_class == SensorStateClass.MEASUREMENT
    assert sensor.entity_description.native_unit_of_measurement == "threats"


async def test_unavailable_when_coordinator_marks_unavailable(
    hass: HomeAssistant,
) -> None:
    """Sensor is unavailable when the coordinator could not fetch data."""
    sensor = _create_sensor(hass, _build_heatmap_data(available=False))
    assert sensor.available is False
