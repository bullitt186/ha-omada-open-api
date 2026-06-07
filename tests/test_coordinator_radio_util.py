"""Tests for OmadaSiteCoordinator._merge_ap_radio_utilization() — TDD Cycle 1."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.omada_open_api.api import OmadaApiError
from custom_components.omada_open_api.const import DEFAULT_RADIO_UTIL_INTERVAL
from custom_components.omada_open_api.coordinator import OmadaSiteCoordinator

from .conftest import TEST_SITE_ID, TEST_SITE_NAME

AP_MAC = "AA-BB-CC-DD-EE-01"
AP_MAC_2 = "AA-BB-CC-DD-EE-04"

SAMPLE_RADIO_RESPONSE = {
    "wp2g": {
        "txUtil": 45,
        "rxUtil": 30,
        "interUtil": 10,
        "busyUtil": 55,
        "actualChannel": "6",
        "txPower": 20,
        "bandWidth": "20MHz",
    },
    "wp5g": {
        "txUtil": 20,
        "rxUtil": 15,
        "interUtil": 5,
        "busyUtil": 25,
        "actualChannel": "36",
        "txPower": 23,
        "bandWidth": "80MHz",
    },
    "wp5g2": {
        "txUtil": 0,
        "rxUtil": 0,
        "interUtil": 0,
        "busyUtil": 0,
        "actualChannel": "149",
        "txPower": 23,
        "bandWidth": "80MHz",
    },
    "wp6g": {
        "txUtil": 10,
        "rxUtil": 8,
        "interUtil": 2,
        "busyUtil": None,
        "actualChannel": "37",
        "txPower": 25,
        "bandWidth": "160MHz",
    },
}


def _make_coordinator(
    hass: HomeAssistant, api_client: MagicMock
) -> OmadaSiteCoordinator:
    """Create a fresh site coordinator with the given mock API client."""
    return OmadaSiteCoordinator(
        hass=hass,
        api_client=api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )


def _ap_devices(*macs: str) -> dict[str, dict]:
    """Return a devices dict with AP entries for the given MACs."""
    return {mac: {"type": "ap", "mac": mac} for mac in macs}


# ---------------------------------------------------------------------------
# Merging values into device data
# ---------------------------------------------------------------------------


async def test_merge_radio_util_2g_values(hass: HomeAssistant) -> None:
    """Test that wp2g utilization values are merged into devices[mac]."""
    api_client = MagicMock()
    api_client.get_ap_radios = AsyncMock(return_value=SAMPLE_RADIO_RESPONSE)
    coordinator = _make_coordinator(hass, api_client)
    devices = _ap_devices(AP_MAC)

    await coordinator._merge_ap_radio_utilization(devices)  # noqa: SLF001

    assert devices[AP_MAC]["radio_tx_util_2g"] == 45
    assert devices[AP_MAC]["radio_rx_util_2g"] == 30
    assert devices[AP_MAC]["radio_inter_util_2g"] == 10
    assert devices[AP_MAC]["radio_busy_util_2g"] == 55


async def test_merge_radio_util_5g_values(hass: HomeAssistant) -> None:
    """Test that wp5g utilization values are merged into devices[mac]."""
    api_client = MagicMock()
    api_client.get_ap_radios = AsyncMock(return_value=SAMPLE_RADIO_RESPONSE)
    coordinator = _make_coordinator(hass, api_client)
    devices = _ap_devices(AP_MAC)

    await coordinator._merge_ap_radio_utilization(devices)  # noqa: SLF001

    assert devices[AP_MAC]["radio_tx_util_5g"] == 20
    assert devices[AP_MAC]["radio_rx_util_5g"] == 15
    assert devices[AP_MAC]["radio_inter_util_5g"] == 5
    assert devices[AP_MAC]["radio_busy_util_5g"] == 25


async def test_merge_radio_util_5g2_values(hass: HomeAssistant) -> None:
    """Test that wp5g2 utilization values (all zero) are merged."""
    api_client = MagicMock()
    api_client.get_ap_radios = AsyncMock(return_value=SAMPLE_RADIO_RESPONSE)
    coordinator = _make_coordinator(hass, api_client)
    devices = _ap_devices(AP_MAC)

    await coordinator._merge_ap_radio_utilization(devices)  # noqa: SLF001

    assert devices[AP_MAC]["radio_tx_util_5g2"] == 0
    assert devices[AP_MAC]["radio_rx_util_5g2"] == 0
    assert devices[AP_MAC]["radio_inter_util_5g2"] == 0
    assert devices[AP_MAC]["radio_busy_util_5g2"] == 0


async def test_merge_radio_util_6g_values(hass: HomeAssistant) -> None:
    """Test that wp6g utilization values are merged (busyUtil None for non-MTK)."""
    api_client = MagicMock()
    api_client.get_ap_radios = AsyncMock(return_value=SAMPLE_RADIO_RESPONSE)
    coordinator = _make_coordinator(hass, api_client)
    devices = _ap_devices(AP_MAC)

    await coordinator._merge_ap_radio_utilization(devices)  # noqa: SLF001

    assert devices[AP_MAC]["radio_tx_util_6g"] == 10
    assert devices[AP_MAC]["radio_rx_util_6g"] == 8
    assert devices[AP_MAC]["radio_inter_util_6g"] == 2
    assert devices[AP_MAC]["radio_busy_util_6g"] is None


# ---------------------------------------------------------------------------
# Missing bands in the API response
# ---------------------------------------------------------------------------


async def test_missing_band_leaves_keys_absent(hass: HomeAssistant) -> None:
    """Test that bands absent from the API response leave keys absent in devices."""
    api_client = MagicMock()
    # Only 2.4 GHz is present
    api_client.get_ap_radios = AsyncMock(
        return_value={
            "wp2g": {"txUtil": 10, "rxUtil": 5, "interUtil": 2, "busyUtil": 12}
        }
    )
    coordinator = _make_coordinator(hass, api_client)
    devices = _ap_devices(AP_MAC)

    await coordinator._merge_ap_radio_utilization(devices)  # noqa: SLF001

    # 2.4 GHz keys should be present
    assert "radio_tx_util_2g" in devices[AP_MAC]
    # 5 GHz keys should be absent
    assert "radio_tx_util_5g" not in devices[AP_MAC]
    assert "radio_tx_util_5g2" not in devices[AP_MAC]
    assert "radio_tx_util_6g" not in devices[AP_MAC]


async def test_empty_response_leaves_all_keys_absent(hass: HomeAssistant) -> None:
    """Test that an empty response leaves all radio util keys absent."""
    api_client = MagicMock()
    api_client.get_ap_radios = AsyncMock(return_value={})
    coordinator = _make_coordinator(hass, api_client)
    devices = _ap_devices(AP_MAC)

    await coordinator._merge_ap_radio_utilization(devices)  # noqa: SLF001

    assert "radio_tx_util_2g" not in devices[AP_MAC]
    assert "radio_tx_util_5g" not in devices[AP_MAC]


# ---------------------------------------------------------------------------
# Non-AP devices are skipped
# ---------------------------------------------------------------------------


async def test_non_ap_devices_are_skipped(hass: HomeAssistant) -> None:
    """Test that switches and gateways do not trigger radio API calls."""
    api_client = MagicMock()
    api_client.get_ap_radios = AsyncMock(return_value=SAMPLE_RADIO_RESPONSE)
    coordinator = _make_coordinator(hass, api_client)
    devices = {
        "SW-MAC": {"type": "switch", "mac": "SW-MAC"},
        "GW-MAC": {"type": "gateway", "mac": "GW-MAC"},
    }

    await coordinator._merge_ap_radio_utilization(devices)  # noqa: SLF001

    api_client.get_ap_radios.assert_not_called()


async def test_no_devices_skips_api(hass: HomeAssistant) -> None:
    """Test that an empty device dict skips all API calls."""
    api_client = MagicMock()
    api_client.get_ap_radios = AsyncMock(return_value={})
    coordinator = _make_coordinator(hass, api_client)

    await coordinator._merge_ap_radio_utilization({})  # noqa: SLF001

    api_client.get_ap_radios.assert_not_called()


# ---------------------------------------------------------------------------
# Multiple APs — one call per AP
# ---------------------------------------------------------------------------


async def test_multiple_aps_each_get_one_call(hass: HomeAssistant) -> None:
    """Test that each AP triggers exactly one get_ap_radios call."""
    api_client = MagicMock()
    api_client.get_ap_radios = AsyncMock(return_value=SAMPLE_RADIO_RESPONSE)
    coordinator = _make_coordinator(hass, api_client)
    devices = _ap_devices(AP_MAC, AP_MAC_2)

    await coordinator._merge_ap_radio_utilization(devices)  # noqa: SLF001

    assert api_client.get_ap_radios.call_count == 2
    called_macs = {c.args[1] for c in api_client.get_ap_radios.call_args_list}
    assert called_macs == {AP_MAC, AP_MAC_2}


# ---------------------------------------------------------------------------
# Caching — second call within interval skips API
# ---------------------------------------------------------------------------


async def test_cache_skips_api_within_interval(hass: HomeAssistant) -> None:
    """Test that a second call within DEFAULT_RADIO_UTIL_INTERVAL skips the API."""
    api_client = MagicMock()
    api_client.get_ap_radios = AsyncMock(return_value=SAMPLE_RADIO_RESPONSE)
    coordinator = _make_coordinator(hass, api_client)
    devices = _ap_devices(AP_MAC)

    # First call — should hit the API
    await coordinator._merge_ap_radio_utilization(devices)  # noqa: SLF001
    assert api_client.get_ap_radios.call_count == 1

    # Second immediate call — should be a cache hit
    await coordinator._merge_ap_radio_utilization(devices)  # noqa: SLF001
    assert api_client.get_ap_radios.call_count == 1  # still 1


async def test_cache_refetches_after_interval(hass: HomeAssistant) -> None:
    """Test that a call after the interval expires re-fetches from the API."""
    api_client = MagicMock()
    api_client.get_ap_radios = AsyncMock(return_value=SAMPLE_RADIO_RESPONSE)
    coordinator = _make_coordinator(hass, api_client)
    devices = _ap_devices(AP_MAC)

    # Simulate the last check being older than the interval
    coordinator._last_radio_util_check = dt.datetime.now(dt.UTC) - dt.timedelta(  # noqa: SLF001
        seconds=DEFAULT_RADIO_UTIL_INTERVAL + 1
    )

    await coordinator._merge_ap_radio_utilization(devices)  # noqa: SLF001

    assert api_client.get_ap_radios.call_count == 1


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


async def test_api_error_logs_warning_and_continues(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that an API error logs a warning and does not raise."""
    api_client = MagicMock()
    api_client.get_ap_radios = AsyncMock(side_effect=OmadaApiError("Timeout"))
    coordinator = _make_coordinator(hass, api_client)
    devices = _ap_devices(AP_MAC)

    # Must not raise
    await coordinator._merge_ap_radio_utilization(devices)  # noqa: SLF001

    assert "radio_tx_util_2g" not in devices[AP_MAC]
    assert any(
        "radio" in r.message.lower() or AP_MAC in r.message for r in caplog.records
    )


async def test_api_error_on_one_ap_does_not_block_others(hass: HomeAssistant) -> None:
    """Test that an API error for one AP still processes the remaining APs."""
    api_client = MagicMock()
    api_client.get_ap_radios = AsyncMock(
        side_effect=[
            OmadaApiError("Timeout"),  # AP_MAC fails
            SAMPLE_RADIO_RESPONSE,  # AP_MAC_2 succeeds
        ]
    )
    coordinator = _make_coordinator(hass, api_client)
    devices = {
        AP_MAC: {"type": "ap", "mac": AP_MAC},
        AP_MAC_2: {"type": "ap", "mac": AP_MAC_2},
    }

    await coordinator._merge_ap_radio_utilization(devices)  # noqa: SLF001

    assert "radio_tx_util_2g" not in devices[AP_MAC]
    assert devices[AP_MAC_2]["radio_tx_util_2g"] == 45


# ---------------------------------------------------------------------------
# actualChannel guard — empty string means band not on hardware
# ---------------------------------------------------------------------------


async def test_band_with_empty_actual_channel_leaves_keys_absent(
    hass: HomeAssistant,
) -> None:
    """Test that a band with actualChannel='' is not merged (radio not on hardware)."""
    api_client = MagicMock()
    api_client.get_ap_radios = AsyncMock(
        return_value={
            "wp2g": {
                "txUtil": 45,
                "rxUtil": 30,
                "interUtil": 10,
                "busyUtil": 55,
                "actualChannel": "6",
            },
            "wp5g2": {
                "txUtil": 0,
                "rxUtil": 0,
                "interUtil": 0,
                "busyUtil": 0,
                "actualChannel": "",  # empty = band not present on hardware
            },
        }
    )
    coordinator = _make_coordinator(hass, api_client)
    devices = _ap_devices(AP_MAC)

    await coordinator._merge_ap_radio_utilization(devices)  # noqa: SLF001

    # 2.4 GHz should be merged (non-empty actualChannel)
    assert devices[AP_MAC]["radio_tx_util_2g"] == 45
    assert devices[AP_MAC]["radio_busy_util_2g"] == 55
    # 5 GHz-2 should NOT be merged (empty actualChannel means no second radio)
    assert "radio_tx_util_5g2" not in devices[AP_MAC]
    assert "radio_rx_util_5g2" not in devices[AP_MAC]
    assert "radio_inter_util_5g2" not in devices[AP_MAC]
    assert "radio_busy_util_5g2" not in devices[AP_MAC]


async def test_band_without_actual_channel_key_is_merged(hass: HomeAssistant) -> None:
    """Test that a band dict lacking the actualChannel key is still merged.

    Some API responses may omit actualChannel; absence ≠ empty channel.
    """
    api_client = MagicMock()
    api_client.get_ap_radios = AsyncMock(
        return_value={
            "wp2g": {"txUtil": 10, "rxUtil": 5, "interUtil": 2, "busyUtil": 12},
        }
    )
    coordinator = _make_coordinator(hass, api_client)
    devices = _ap_devices(AP_MAC)

    await coordinator._merge_ap_radio_utilization(devices)  # noqa: SLF001

    assert devices[AP_MAC]["radio_tx_util_2g"] == 10
    assert devices[AP_MAC]["radio_busy_util_2g"] == 12
