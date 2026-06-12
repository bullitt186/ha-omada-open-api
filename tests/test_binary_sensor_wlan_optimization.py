"""Tests for WLAN optimization status binary sensor (Issue #7)."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.helpers.entity import EntityCategory

from custom_components.omada_open_api.api import OmadaApiClient, OmadaApiError
from custom_components.omada_open_api.binary_sensor import (
    OmadaWlanOptimizationBinarySensor,
)
from custom_components.omada_open_api.const import DOMAIN
from custom_components.omada_open_api.coordinator import OmadaSiteCoordinator

from .conftest import TEST_SITE_ID, TEST_SITE_NAME

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

GATEWAY_MAC = "AA-BB-CC-DD-EE-03"

# WLAN optimization API status values
STATUS_COMPLETED = 0
STATUS_NO_RESULT = 1
STATUS_RUNNING = 2
STATUS_CANCELING = 3


def _make_coordinator(
    hass: HomeAssistant,
    wlan_optimization: dict | None = None,
) -> OmadaSiteCoordinator:
    """Build a coordinator with optional wlan_optimization data."""
    coord = OmadaSiteCoordinator(
        hass=hass,
        api_client=MagicMock(),
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    coord.data = {
        "devices": {
            GATEWAY_MAC: {
                "mac": GATEWAY_MAC,
                "name": "Main Gateway",
                "type": "gateway",
                "status": 1,
            }
        },
        "wlan_optimization": wlan_optimization,
        "site_id": TEST_SITE_ID,
        "site_name": TEST_SITE_NAME,
    }
    return coord


# ---------------------------------------------------------------------------
# OmadaWlanOptimizationBinarySensor — is_on (running state)
# ---------------------------------------------------------------------------


async def test_wlan_optimization_running(hass: HomeAssistant) -> None:
    """Binary sensor is on when status == 2 (running)."""
    coord = _make_coordinator(
        hass,
        wlan_optimization={
            "status": STATUS_RUNNING,
            "beforeIndex": 60,
            "afterIndex": 75,
        },
    )
    sensor = OmadaWlanOptimizationBinarySensor(coordinator=coord, site_id=TEST_SITE_ID)
    assert sensor.is_on is True


async def test_wlan_optimization_not_running_completed(hass: HomeAssistant) -> None:
    """Binary sensor is off when status == 0 (completed/applied)."""
    coord = _make_coordinator(
        hass,
        wlan_optimization={
            "status": STATUS_COMPLETED,
            "beforeIndex": 60,
            "afterIndex": 75,
        },
    )
    sensor = OmadaWlanOptimizationBinarySensor(coordinator=coord, site_id=TEST_SITE_ID)
    assert sensor.is_on is False


async def test_wlan_optimization_not_running_no_result(hass: HomeAssistant) -> None:
    """Binary sensor is off when status == 1 (no result yet)."""
    coord = _make_coordinator(hass, wlan_optimization={"status": STATUS_NO_RESULT})
    sensor = OmadaWlanOptimizationBinarySensor(coordinator=coord, site_id=TEST_SITE_ID)
    assert sensor.is_on is False


async def test_wlan_optimization_canceling(hass: HomeAssistant) -> None:
    """Binary sensor is off when status == 3 (canceling)."""
    coord = _make_coordinator(hass, wlan_optimization={"status": STATUS_CANCELING})
    sensor = OmadaWlanOptimizationBinarySensor(coordinator=coord, site_id=TEST_SITE_ID)
    assert sensor.is_on is False


async def test_wlan_optimization_unavailable_when_none(hass: HomeAssistant) -> None:
    """Binary sensor is unavailable when wlan_optimization data is None."""
    coord = _make_coordinator(hass, wlan_optimization=None)
    sensor = OmadaWlanOptimizationBinarySensor(coordinator=coord, site_id=TEST_SITE_ID)
    assert sensor.available is False


async def test_wlan_optimization_available_when_data_present(
    hass: HomeAssistant,
) -> None:
    """Binary sensor is available when wlan_optimization data is present."""
    coord = _make_coordinator(hass, wlan_optimization={"status": STATUS_COMPLETED})
    sensor = OmadaWlanOptimizationBinarySensor(coordinator=coord, site_id=TEST_SITE_ID)
    assert sensor.available is True


async def test_wlan_optimization_unavailable_on_coordinator_failure(
    hass: HomeAssistant,
) -> None:
    """Binary sensor is unavailable when coordinator update fails."""
    coord = _make_coordinator(hass, wlan_optimization={"status": STATUS_COMPLETED})
    coord.last_update_success = False
    sensor = OmadaWlanOptimizationBinarySensor(coordinator=coord, site_id=TEST_SITE_ID)
    assert sensor.available is False


async def test_wlan_optimization_unique_id(hass: HomeAssistant) -> None:
    """Binary sensor unique_id is site-scoped."""
    coord = _make_coordinator(hass, wlan_optimization={"status": STATUS_COMPLETED})
    sensor = OmadaWlanOptimizationBinarySensor(coordinator=coord, site_id=TEST_SITE_ID)
    assert sensor.unique_id == f"{TEST_SITE_ID}_wlan_optimization_running"


async def test_wlan_optimization_device_info_links_to_site_device(
    hass: HomeAssistant,
) -> None:
    """Binary sensor device_info identifier matches the site device (site_{site_id})."""
    coord = _make_coordinator(hass, wlan_optimization={"status": STATUS_COMPLETED})
    sensor = OmadaWlanOptimizationBinarySensor(coordinator=coord, site_id=TEST_SITE_ID)
    identifiers = sensor.device_info["identifiers"]  # type: ignore[index]
    assert (DOMAIN, f"site_{TEST_SITE_ID}") in identifiers


async def test_wlan_optimization_entity_category_diagnostic(
    hass: HomeAssistant,
) -> None:
    """Binary sensor has DIAGNOSTIC entity_category."""
    coord = _make_coordinator(hass, wlan_optimization={"status": STATUS_COMPLETED})
    sensor = OmadaWlanOptimizationBinarySensor(coordinator=coord, site_id=TEST_SITE_ID)
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC


# ---------------------------------------------------------------------------
# API: get_wlan_optimization_status
# ---------------------------------------------------------------------------


async def test_api_get_wlan_optimization_status_calls_correct_url() -> None:
    """get_wlan_optimization_status calls the RF planning result endpoint."""
    expected_result = {"status": 0, "beforeIndex": 55, "afterIndex": 80}

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
            client_secret="csec",  # noqa: S106
            access_token="tok",  # noqa: S106
            refresh_token="rtok",  # noqa: S106
            token_expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
        )
        result = await real_client.get_wlan_optimization_status("site_001")

    assert result == expected_result
    mock_req.assert_called_once()
    call_url = mock_req.call_args[0][1]
    assert "radio-frequency-planning/result" in call_url
    assert "site_001" in call_url


# ---------------------------------------------------------------------------
# Coordinator: wlan_optimization data is fetched and stored
# ---------------------------------------------------------------------------


def _build_minimal_mock_api() -> MagicMock:
    """Build a minimal mock API client for coordinator tests."""
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
    mock_api.get_firmware_info = AsyncMock(return_value={})
    mock_api.get_switch_port_details = AsyncMock(return_value=[])
    return mock_api


async def test_coordinator_fetches_wlan_optimization(hass: HomeAssistant) -> None:
    """OmadaSiteCoordinator stores wlan_optimization in coordinator.data."""
    wlan_result = {"status": 0, "beforeIndex": 55, "afterIndex": 80}
    mock_api = _build_minimal_mock_api()
    mock_api.get_wlan_optimization_status = AsyncMock(return_value=wlan_result)

    coord = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    data = await coord._async_update_data()  # noqa: SLF001

    assert "wlan_optimization" in data
    assert data["wlan_optimization"] == wlan_result
    mock_api.get_wlan_optimization_status.assert_called_once_with(TEST_SITE_ID)


async def test_coordinator_wlan_optimization_none_on_api_error(
    hass: HomeAssistant,
) -> None:
    """wlan_optimization is None when the API call fails."""
    mock_api = _build_minimal_mock_api()
    mock_api.get_wlan_optimization_status = AsyncMock(
        side_effect=OmadaApiError("API unavailable")
    )

    coord = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )

    data = await coord._async_update_data()  # noqa: SLF001

    assert data["wlan_optimization"] is None
