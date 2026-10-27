"""Config and options flow texts are translatable (quality scale: config-flow)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.omada_open_api.const import (
    CONTROLLER_TYPE_CLOUD,
    CONTROLLER_TYPE_FUSION,
    CONTROLLER_TYPE_LOCAL,
    REGIONS,
)

COMP_DIR = Path(__file__).parent.parent / "custom_components" / "omada_open_api"
STRINGS = json.loads((COMP_DIR / "strings.json").read_text())
STEPS = [
    (flow, step_id, step)
    for flow in ("config", "options")
    for step_id, step in STRINGS[flow]["step"].items()
    if "data" in step
]


@pytest.mark.parametrize(
    ("flow", "step_id", "step"), STEPS, ids=[f"{f}.{s}" for f, s, _ in STEPS]
)
def test_every_field_has_description(flow: str, step_id: str, step: dict) -> None:
    """Every form field explains itself via data_description."""
    assert set(step.get("data_description", {})) == set(step["data"])


def test_select_labels_are_translated() -> None:
    """Controller type and region labels come from the selector block."""
    selector = STRINGS["selector"]
    assert set(selector["controller_type"]["options"]) == {
        CONTROLLER_TYPE_LOCAL,
        CONTROLLER_TYPE_CLOUD,
        CONTROLLER_TYPE_FUSION,
    }
    assert set(selector["region"]["options"]) == set(REGIONS)


def test_no_hardcoded_choice_labels() -> None:
    """The flow uses translated selectors instead of vol.In label maps."""
    assert "vol.In(" not in (COMP_DIR / "config_flow.py").read_text()
