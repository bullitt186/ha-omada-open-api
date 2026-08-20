"""Tests for gateway WAN speed-test sensors."""

from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock

from custom_components.omada_open_api.sensor import (
    OmadaWanSpeedTestSensor,
    _setup_wan_speed_test_sensors,
)


def test_wan_speed_test_download_sensor_uses_selected_port_result() -> None:
    """The download sensor reads the latest result for its WAN port."""
    coordinator = MagicMock()
    coordinator.data = {
        "portSpeedResults": [
            {
                "portId": "1_gateway-mac",
                "portName": "WAN1",
                "down": 987_000_000,
                "up": 123_000_000,
                "latency": 7,
                "time": 1_787_226_476,
                "status": 1,
            }
        ]
    }
    coordinator.last_update_success = True

    sensor = OmadaWanSpeedTestSensor(
        coordinator=coordinator,
        gateway_mac="gateway-mac",
        port_id="1_gateway-mac",
        port_name="WAN1",
        metric="download",
    )

    assert sensor.native_value == 987_000_000
    assert sensor.available is True


def test_wan_speed_test_last_test_sensor_converts_epoch_seconds() -> None:
    """The last-test sensor exposes Omada's epoch timestamp in UTC."""
    coordinator = MagicMock()
    coordinator.data = {
        "portSpeedResults": [
            {"portId": "1_gateway-mac", "portName": "WAN1", "time": 1_787_226_476}
        ]
    }
    coordinator.last_update_success = True

    sensor = OmadaWanSpeedTestSensor(
        coordinator, "gateway-mac", "1_gateway-mac", "WAN1", "last_test"
    )

    assert sensor.native_value == dt.datetime.fromtimestamp(1_787_226_476, tz=dt.UTC)


def test_wan_speed_test_sensors_are_added_when_result_arrives() -> None:
    """The first result dynamically adds the four per-port result sensors."""
    coordinator = MagicMock()
    coordinator.data = {"portSpeedResults": []}
    listeners = []
    coordinator.async_add_listener.side_effect = listeners.append
    entry = MagicMock()
    entities = []

    _setup_wan_speed_test_sensors(
        {("site-id", "gateway-mac"): coordinator}, entities.extend, entry
    )

    assert entities == []
    coordinator.data = {
        "portSpeedResults": [{"portId": "1_gateway-mac", "portName": "WAN1"}]
    }
    listeners[0]()

    assert len(entities) == 4
    assert {entity.unique_id for entity in entities} == {
        f"gateway-mac_1_gateway-mac_wan_speed_test_{metric}"
        for metric in ("download", "upload", "latency", "last_test")
    }


def test_wan_speed_test_sensors_are_created_for_known_wan_port() -> None:
    """Known WAN ports expose result sensors before their first test finishes."""
    coordinator = MagicMock()
    coordinator.data = {
        "portSpeedResults": [],
        "ports": [{"port": 1, "portUuid": "1_opaque-port-id", "name": "WAN1"}],
    }
    coordinator.async_add_listener.return_value = lambda: None
    entry = MagicMock()
    entities = []

    _setup_wan_speed_test_sensors(
        {("site-id", "gateway-mac"): coordinator},
        entities.extend,
        entry,
    )

    assert len(entities) == 4
