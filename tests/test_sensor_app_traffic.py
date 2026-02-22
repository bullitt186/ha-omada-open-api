"""Tests for app traffic sensor entities."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.const import UnitOfInformation

from custom_components.omada_open_api.const import DOMAIN
from custom_components.omada_open_api.sensor import (
    OmadaClientAppTrafficSensor,
    _auto_scale_bytes,
)

from .conftest import TEST_SITE_ID

# ---------------------------------------------------------------------------
# _auto_scale_bytes unit tests
# ---------------------------------------------------------------------------


def test_auto_scale_bytes_none() -> None:
    """Test auto-scale with None returns None pair."""
    value, unit = _auto_scale_bytes(None)
    assert value is None
    assert unit is None


def test_auto_scale_bytes_zero() -> None:
    """Test auto-scale with zero bytes."""
    value, unit = _auto_scale_bytes(0)
    assert value == 0.0
    assert unit == UnitOfInformation.BYTES


def test_auto_scale_bytes_bytes_range() -> None:
    """Test auto-scale in bytes range (<1000)."""
    value, unit = _auto_scale_bytes(500)
    assert value == 500.0
    assert unit == UnitOfInformation.BYTES


def test_auto_scale_bytes_kilobytes() -> None:
    """Test auto-scale in kilobytes range."""
    value, unit = _auto_scale_bytes(5_000)
    assert value == 5.0
    assert unit == UnitOfInformation.KILOBYTES


def test_auto_scale_bytes_megabytes() -> None:
    """Test auto-scale in megabytes range."""
    value, unit = _auto_scale_bytes(5_000_000)
    assert value == 5.0
    assert unit == UnitOfInformation.MEGABYTES


def test_auto_scale_bytes_gigabytes() -> None:
    """Test auto-scale in gigabytes range."""
    value, unit = _auto_scale_bytes(5_000_000_000)
    assert value == 5.0
    assert unit == UnitOfInformation.GIGABYTES


def test_auto_scale_bytes_terabytes() -> None:
    """Test auto-scale in terabytes range."""
    value, unit = _auto_scale_bytes(5_000_000_000_000)
    assert value == 5.0
    assert unit == UnitOfInformation.TERABYTES


# ---------------------------------------------------------------------------
# OmadaClientAppTrafficSensor tests
# ---------------------------------------------------------------------------


def _make_coordinator(data: dict | None = None) -> MagicMock:
    """Create a minimal mock coordinator for app traffic sensor."""
    coordinator = MagicMock()
    coordinator.data = data or {}
    coordinator.last_update_success = True
    coordinator.site_id = TEST_SITE_ID
    return coordinator


def test_app_traffic_sensor_init() -> None:
    """Test app traffic sensor initialization sets correct attributes."""
    coordinator = _make_coordinator()
    sensor = OmadaClientAppTrafficSensor(
        coordinator=coordinator,
        client_mac="11-22-33-44-55-AA",
        app_id="100",
        app_name="YouTube",
        metric_type="download",
    )

    assert sensor._attr_unique_id == "11-22-33-44-55-AA_100_download_app_traffic"  # noqa: SLF001
    assert sensor._attr_name == "YouTube Download"  # noqa: SLF001
    assert sensor._attr_icon == "mdi:download-network"  # noqa: SLF001
    assert sensor._attr_device_info["identifiers"] == {(DOMAIN, "11-22-33-44-55-AA")}  # noqa: SLF001


def test_app_traffic_sensor_upload_icon() -> None:
    """Test that upload metric type sets upload icon."""
    coordinator = _make_coordinator()
    sensor = OmadaClientAppTrafficSensor(
        coordinator=coordinator,
        client_mac="11-22-33-44-55-AA",
        app_id="100",
        app_name="YouTube",
        metric_type="upload",
    )

    assert sensor._attr_icon == "mdi:upload-network"  # noqa: SLF001
    assert sensor._attr_name == "YouTube Upload"  # noqa: SLF001


def test_app_traffic_sensor_native_value() -> None:
    """Test native_value returns auto-scaled value."""
    coordinator = _make_coordinator(
        {
            "11-22-33-44-55-AA": {
                "100": {
                    "download": 5_000_000,
                    "upload": 1_000,
                    "app_name": "YouTube",
                }
            }
        }
    )
    sensor = OmadaClientAppTrafficSensor(
        coordinator=coordinator,
        client_mac="11-22-33-44-55-AA",
        app_id="100",
        app_name="YouTube",
        metric_type="download",
    )

    assert sensor.native_value == 5.0
    assert sensor._attr_native_unit_of_measurement == UnitOfInformation.MEGABYTES  # noqa: SLF001


def test_app_traffic_sensor_native_value_no_data() -> None:
    """Test native_value when no data exists returns 0 scaled."""
    coordinator = _make_coordinator({})
    sensor = OmadaClientAppTrafficSensor(
        coordinator=coordinator,
        client_mac="11-22-33-44-55-AA",
        app_id="100",
        app_name="YouTube",
        metric_type="download",
    )

    # No client data → raw_bytes defaults to 0
    assert sensor.native_value == 0.0


def test_app_traffic_sensor_extra_state_attributes() -> None:
    """Test extra_state_attributes returns expected fields."""
    coordinator = _make_coordinator(
        {
            "11-22-33-44-55-AA": {
                "100": {
                    "download": 5_000_000,
                    "upload": 1_000_000,
                    "app_name": "YouTube",
                    "app_description": "Video streaming",
                    "family": "Streaming Media",
                    "traffic": 6_000_000,
                }
            }
        }
    )
    sensor = OmadaClientAppTrafficSensor(
        coordinator=coordinator,
        client_mac="11-22-33-44-55-AA",
        app_id="100",
        app_name="YouTube",
        metric_type="download",
    )

    attrs = sensor.extra_state_attributes
    assert attrs["application_id"] == "100"
    assert attrs["application_name"] == "YouTube"
    assert attrs["raw_bytes"] == 5_000_000
    assert attrs["application_description"] == "Video streaming"
    assert attrs["family"] == "Streaming Media"
    assert attrs["total_traffic_bytes"] == 6_000_000
    assert "total_traffic" in attrs


def test_app_traffic_sensor_extra_state_attributes_minimal() -> None:
    """Test extra_state_attributes with minimal data."""
    coordinator = _make_coordinator(
        {
            "11-22-33-44-55-AA": {
                "100": {
                    "download": 100,
                    "app_name": "YouTube",
                }
            }
        }
    )
    sensor = OmadaClientAppTrafficSensor(
        coordinator=coordinator,
        client_mac="11-22-33-44-55-AA",
        app_id="100",
        app_name="YouTube",
        metric_type="download",
    )

    attrs = sensor.extra_state_attributes
    assert "application_description" not in attrs
    assert "family" not in attrs
    assert "total_traffic_bytes" not in attrs


def test_app_traffic_sensor_available_true() -> None:
    """Test available when coordinator has data."""
    coordinator = _make_coordinator(
        {"11-22-33-44-55-AA": {"100": {"download": 0, "upload": 0}}}
    )
    sensor = OmadaClientAppTrafficSensor(
        coordinator=coordinator,
        client_mac="11-22-33-44-55-AA",
        app_id="100",
        app_name="YouTube",
        metric_type="download",
    )

    assert sensor.available is True


def test_app_traffic_sensor_unavailable_no_app_data() -> None:
    """Test unavailable when app data is missing."""
    coordinator = _make_coordinator(
        {"11-22-33-44-55-AA": {}}  # No app data
    )
    sensor = OmadaClientAppTrafficSensor(
        coordinator=coordinator,
        client_mac="11-22-33-44-55-AA",
        app_id="100",
        app_name="YouTube",
        metric_type="download",
    )

    assert sensor.available is False


def test_app_traffic_sensor_unavailable_coordinator_failed() -> None:
    """Test unavailable when coordinator update failed."""
    coordinator = _make_coordinator()
    coordinator.last_update_success = False
    sensor = OmadaClientAppTrafficSensor(
        coordinator=coordinator,
        client_mac="11-22-33-44-55-AA",
        app_id="100",
        app_name="YouTube",
        metric_type="download",
    )

    assert sensor.available is False
