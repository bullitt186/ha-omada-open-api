"""Test the device-info paths against the post-deprecation attribute API."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

from homeassistant.helpers import device_registry as dr
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.omada_open_api import device_tracker, devices
from custom_components.omada_open_api.const import DOMAIN
from custom_components.omada_open_api.entity import build_linked_infra_device_info
from custom_components.omada_open_api.sensor import CLIENT_SENSORS, OmadaClientSensor

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

DEVICE_MAC = "AA-BB-CC-DD-EE-01"
UPLINK_MAC = "AA-BB-CC-DD-EE-02"
API_URL = "https://omada.example"


@pytest.fixture
def attribute_only_device_info(monkeypatch: pytest.MonkeyPatch) -> None:
    """Supply keyword-only metadata with no dictionary compatibility layer."""
    monkeypatch.setattr(devices, "DeviceInfo", SimpleNamespace)
    monkeypatch.setattr(device_tracker, "DeviceInfo", SimpleNamespace)


@pytest.mark.parametrize("uplink", ["registered-uplink", None])
def test_client_info_parent(
    attribute_only_device_info: None, uplink: str | None
) -> None:
    """Client metadata includes only a known parent ID."""
    info = devices.build_client_device_info(
        DEVICE_MAC, {"name": "Client"}, API_URL, uplink
    )

    assert info.name == "Client"
    assert info.connections == {(dr.CONNECTION_NETWORK_MAC, DEVICE_MAC)}
    if uplink is None:
        assert not hasattr(info, "via_device_id")
    else:
        assert info.via_device_id == uplink


@pytest.mark.parametrize(
    ("device_type", "registered", "linked"),
    [
        ("ap", True, True),
        ("ap", False, False),
        ("gateway", True, False),
        ("router", True, False),
    ],
)
async def test_infrastructure_info_parent(
    hass: HomeAssistant,
    attribute_only_device_info: None,
    device_type: str,
    registered: bool,
    linked: bool,
) -> None:
    """Only non-routing infrastructure devices link to registered uplinks."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    coordinator = MagicMock(hass=hass, config_entry=entry)
    coordinator.api_client.api_url = API_URL
    coordinator.data = {
        "devices": {
            DEVICE_MAC: {
                "name": "Device",
                "type": device_type,
                "uplink_device_mac": UPLINK_MAC,
            }
        }
    }
    if registered:
        uplink = dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={(DOMAIN, UPLINK_MAC)}
        )

    info = build_linked_infra_device_info(coordinator, DEVICE_MAC)

    assert info.identifiers == {(DOMAIN, DEVICE_MAC)}
    if linked:
        assert info.via_device_id == uplink.id
    else:
        assert not hasattr(info, "via_device_id")


@pytest.mark.parametrize(
    ("hostname", "registered", "expected_name"),
    [
        ("Access point", False, "Access point"),
        (None, False, "aa:bb:cc:dd:ee:01"),
        (None, True, None),
    ],
)
async def test_infrastructure_tracker_info_name(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    attribute_only_device_info: None,
    hostname: str | None,
    registered: bool,
    expected_name: str | None,
) -> None:
    """The scanner uses the hostname or MAC and preserves an existing name."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    coordinator = MagicMock(hass=hass, config_entry=entry)
    coordinator.data = {"devices": {DEVICE_MAC: {"name": hostname}}}
    tracker = device_tracker.OmadaDeviceTracker(coordinator, DEVICE_MAC)
    tracker.hass = hass
    tracker.platform = MagicMock(config_entry=entry)
    mac = "aa:bb:cc:dd:ee:01"
    if registered:
        dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id,
            connections={(dr.CONNECTION_NETWORK_MAC, mac)},
            name="Saved name",
        )
    monkeypatch.setattr(device_tracker, "MAJOR_VERSION", 2026)
    monkeypatch.setattr(device_tracker, "MINOR_VERSION", 11)
    monkeypatch.setattr(
        device_tracker.ScannerEntity, "async_prepare_to_add_to_hass", AsyncMock()
    )

    await tracker.async_prepare_to_add_to_hass()

    info = tracker._attr_device_info
    assert info is not None
    assert info.connections == {(dr.CONNECTION_NETWORK_MAC, mac)}
    if expected_name is None:
        assert not hasattr(info, "name")
    else:
        assert info.name == expected_name


def test_signal_strength_debug_uses_client_name(
    attribute_only_device_info: None, caplog: pytest.LogCaptureFixture
) -> None:
    """The signal-strength sensor logs the same fallback name as the record."""
    coordinator = MagicMock(site_device_id=None)
    coordinator.api_client.api_url = API_URL
    coordinator.data = {DEVICE_MAC: {"host_name": "client-host"}}
    description = next(d for d in CLIENT_SENSORS if d.key == "signal_strength")

    with caplog.at_level("DEBUG", logger=OmadaClientSensor.__module__):
        sensor = OmadaClientSensor(coordinator, description, DEVICE_MAC)

    assert sensor.device_info is not None
    assert sensor.device_info.name == "client-host"
    assert (
        "Client device client-host: parent=None, via_device_id=None" in caplog.messages
    )
