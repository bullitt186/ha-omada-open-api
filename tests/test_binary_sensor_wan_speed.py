"""Tests for WAN speed-test progress binary sensors."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.omada_open_api.binary_sensor import (
    OmadaWanSpeedTestRunningBinarySensor,
)


def test_wan_speed_test_running_sensor_tracks_fusion_running_status() -> None:
    """Fusion status 2 reports an in-progress speed test."""
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.data = {
        "activePortResults": [{"portId": 1, "status": 2, "progress": 0.5}]
    }

    sensor = OmadaWanSpeedTestRunningBinarySensor(
        coordinator, "gateway-mac", "1", "WAN1"
    )

    assert sensor.is_on is True
    assert sensor.available is True


def test_wan_speed_test_running_sensor_is_off_when_idle() -> None:
    """Fusion returns an off state when no test is running for the port."""
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.data = {"activePortResults": []}

    sensor = OmadaWanSpeedTestRunningBinarySensor(
        coordinator, "gateway-mac", "1", "WAN1"
    )

    assert sensor.is_on is False
