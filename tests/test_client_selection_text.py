"""Tests for the client selection step descriptions."""

import json
from pathlib import Path

import pytest

COMPONENT_DIR = Path(__file__).parents[1] / "custom_components" / "omada_open_api"


@pytest.mark.parametrize("relative_path", ["strings.json", "translations/en.json"])
@pytest.mark.parametrize(
    ("section", "step"), [("config", "clients"), ("options", "client_selection")]
)
def test_client_selection_text_has_no_200_client_limit(
    relative_path: str, section: str, step: str
) -> None:
    """The client list is no longer capped, so the text must not claim it (GH #96)."""
    content = json.loads((COMPONENT_DIR / relative_path).read_text())
    description = content[section]["step"][step]["description"]

    assert "first 200 clients" not in description
