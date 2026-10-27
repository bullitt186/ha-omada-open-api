"""Icons come from icons.json only (quality scale: icon-translations)."""

from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

COMP_DIR = Path(__file__).parent.parent / "custom_components" / "omada_open_api"
PLATFORMS = ("sensor", "binary_sensor", "switch", "button", "update")

HARDCODED_ICON = re.compile(r"_attr_icon\s*=|\bicon=|def icon\(")


@pytest.fixture(scope="module")
def icons() -> dict:
    """Load icons.json."""
    return json.loads((COMP_DIR / "icons.json").read_text())


@pytest.mark.parametrize("platform", PLATFORMS)
def test_no_hardcoded_icons(platform: str) -> None:
    """Platform modules must not set icons in code."""
    src = (COMP_DIR / f"{platform}.py").read_text()
    assert not HARDCODED_ICON.search(src), f"{platform}.py sets icons in code"


def test_no_icon_constants() -> None:
    """const.py must not carry mdi: icon strings."""
    assert "mdi:" not in (COMP_DIR / "const.py").read_text()


@pytest.mark.parametrize(
    ("platform", "key"),
    [
        ("button", "wan_speed_test"),
        ("sensor", "threat_heatmap_daily"),
        ("sensor", "threat_heatmap_weekly"),
        ("sensor", "threat_heatmap_monthly"),
        ("sensor", "app_upload"),
        ("sensor", "app_download"),
        ("sensor", "poe_power"),
        ("switch", "ssid_broadcast"),
        ("switch", "ap_ssid"),
    ],
)
def test_icon_defined(icons: dict, platform: str, key: str) -> None:
    """Keys whose icons were previously hardcoded exist in icons.json."""
    assert "default" in icons["entity"][platform][key]


@pytest.mark.parametrize("key", ["ssid_broadcast", "ap_ssid"])
def test_ssid_switch_off_icon(icons: dict, key: str) -> None:
    """SSID switches keep the wifi-off state icon."""
    assert icons["entity"]["switch"][key]["state"]["off"] == "mdi:wifi-off"
