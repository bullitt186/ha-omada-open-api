"""Raised HA exceptions are translatable (quality scale: exception-translations)."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import re

import pytest

COMP_DIR = Path(__file__).parent.parent / "custom_components" / "omada_open_api"
EXCEPTIONS = {
    "HomeAssistantError",
    "ServiceValidationError",
    "ConfigEntryNotReady",
    "ConfigEntryAuthFailed",
}


def _raises() -> list[tuple[str, int, ast.Call]]:
    return [
        (path.name, node.lineno, node.exc)
        for path in sorted(COMP_DIR.glob("*.py"))
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Raise)
        and isinstance(node.exc, ast.Call)
        and isinstance(node.exc.func, ast.Name)
        and node.exc.func.id in EXCEPTIONS
    ]


RAISES = _raises()


@pytest.fixture(scope="module")
def exceptions() -> dict:
    """Load the exceptions section of strings.json."""
    return json.loads((COMP_DIR / "strings.json").read_text())["exceptions"]


@pytest.mark.parametrize(("file", "line", "call"), RAISES)
def test_raise_is_translated(exceptions: dict, file: str, line: int, call) -> None:
    """Every raise uses a known translation key with matching placeholders."""
    kw = {k.arg: k.value for k in call.keywords}
    where = f"{file}:{line}"
    assert not call.args, f"{where} passes a plain message"
    assert isinstance(kw.get("translation_domain"), ast.Name), where
    key = kw.get("translation_key")
    assert isinstance(key, ast.Constant), f"{where} has no literal translation_key"
    assert key.value in exceptions, f"{where} key {key.value!r} not in strings.json"

    wanted = set(re.findall(r"{(\w+)}", exceptions[key.value]["message"]))
    given: set[str] = set()
    if isinstance(ph := kw.get("translation_placeholders"), ast.Dict):
        given = {str(k.value) for k in ph.keys if isinstance(k, ast.Constant)}
    assert given == wanted, f"{where} placeholders {given} != {wanted}"


def test_translations_in_sync() -> None:
    """translations/en.json mirrors strings.json."""
    strings = json.loads((COMP_DIR / "strings.json").read_text())
    en = json.loads((COMP_DIR / "translations" / "en.json").read_text())
    assert strings["exceptions"] == en["exceptions"]
