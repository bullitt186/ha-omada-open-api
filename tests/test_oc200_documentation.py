"""Tests for OC200 Open API support documentation."""

import json
from pathlib import Path

import pytest

COMPONENT_DIR = Path(__file__).parents[1] / "custom_components" / "omada_open_api"


@pytest.mark.parametrize(
    "relative_path",
    ["strings.json", "translations/en.json"],
)
def test_oc200_support_text_is_firmware_aware(relative_path: str) -> None:
    """OC200 guidance reflects firmware-dependent Open API support."""
    content = json.loads((COMPONENT_DIR / relative_path).read_text())
    description = content["config"]["step"]["user"]["description"]
    cloud_error = content["config"]["error"]["controller_id_not_found_free_tier"]

    assert "firmware 6.2.10.18" in description
    assert "OC200 on supported firmware" in cloud_error
    assert "OC200 does not support Open API" not in description
    assert "not OC200" not in cloud_error
