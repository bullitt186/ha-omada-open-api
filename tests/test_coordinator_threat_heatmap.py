"""Tests for OmadaThreatHeatmapCoordinator."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.omada_open_api.api import OmadaApiError
from custom_components.omada_open_api.coordinator import OmadaThreatHeatmapCoordinator

from .conftest import TEST_SITE_ID, TEST_SITE_NAME

ROW_US = {
    "time": 100,
    "srcLatitude": 38.0,
    "srcLongitude": -97.0,
    "srcCountry": "US",
    "srcIp": "1.1.1.1",
    "signature": "ET EXPLOIT Foo",
    "activity": "Scan",
    "severity": 1,
}
ROW_NO_COORDS = {"time": 50, "srcLatitude": None, "srcLongitude": None}


async def _make_coordinator(
    hass: HomeAssistant, mock_api_client: MagicMock, window: str = "daily"
) -> OmadaThreatHeatmapCoordinator:
    return OmadaThreatHeatmapCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
        window=window,
    )


async def test_fetches_and_aggregates_points(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Coordinator fetches rows and exposes the aggregated attribute contract."""
    mock_api_client.get_threat_management = AsyncMock(
        return_value=[ROW_US, ROW_NO_COORDS]
    )
    coordinator = await _make_coordinator(hass, mock_api_client)

    await coordinator.async_refresh()
    data = coordinator.data

    assert data["source"] == "omada_open_api.security.threat-management"
    assert data["site_id"] == TEST_SITE_ID
    assert data["site_name"] == TEST_SITE_NAME
    assert data["window"] == "daily"
    assert data["window_end"] - data["window_start"] == 86400
    assert data["total_rows"] == 2
    assert data["fetched_rows"] == 2
    assert data["skipped_rows"] == 1
    assert data["max"] == 1
    assert len(data["points"]) == 1
    assert data["points"][0]["country"] == "US"
    assert data["available"] is True


async def test_hourly_window_seconds(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Hourly coordinator window spans 60 minutes."""
    mock_api_client.get_threat_management = AsyncMock(return_value=[])
    coordinator = await _make_coordinator(hass, mock_api_client, window="hourly")

    await coordinator.async_refresh()

    assert coordinator.data["window_end"] - coordinator.data["window_start"] == 3600
    assert coordinator.data["window"] == "hourly"


async def test_weekly_window_seconds(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """Weekly coordinator window spans 7 days."""
    mock_api_client.get_threat_management = AsyncMock(return_value=[])
    coordinator = await _make_coordinator(hass, mock_api_client, window="weekly")

    await coordinator.async_refresh()

    assert (
        coordinator.data["window_end"] - coordinator.data["window_start"] == 7 * 86400
    )
    assert coordinator.data["total_rows"] == 0
    assert coordinator.data["max"] == 0
    assert coordinator.data["points"] == []


async def test_endpoint_error_marks_unavailable_without_failing_refresh(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """A 404/unsupported endpoint error marks data unavailable, not a refresh failure."""
    mock_api_client.get_threat_management = AsyncMock(
        side_effect=OmadaApiError("HTTP 404: not found")
    )
    coordinator = await _make_coordinator(hass, mock_api_client)

    await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    assert coordinator.data["available"] is False
    assert coordinator.data["points"] == []


async def test_error_after_success_keeps_last_good_data(
    hass: HomeAssistant, mock_api_client: MagicMock
) -> None:
    """A later failure preserves the previously fetched data."""
    mock_api_client.get_threat_management = AsyncMock(return_value=[ROW_US])
    coordinator = await _make_coordinator(hass, mock_api_client)
    await coordinator.async_refresh()
    assert coordinator.data["available"] is True
    assert len(coordinator.data["points"]) == 1

    mock_api_client.get_threat_management = AsyncMock(side_effect=OmadaApiError("boom"))
    await coordinator.async_refresh()

    assert coordinator.data["available"] is True
    assert len(coordinator.data["points"]) == 1
