"""Tests for scripts/mutation_report.py, the mutmut result summary."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "mutation_report.py"
SERVICES = "custom_components/omada_open_api/services.py"
API = "custom_components/omada_open_api/api.py"


@pytest.fixture
def report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Load the script with the working directory in an empty folder."""
    spec = importlib.util.spec_from_file_location("mutation_report", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.chdir(tmp_path)
    return module


def write_meta(module: str, exit_code_by_key: dict[str, int | None]) -> None:
    """Write a .meta file in the format mutmut 3 uses."""
    meta = Path("mutants") / f"{module}.meta"
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text(json.dumps({"exit_code_by_key": exit_code_by_key}))


def run(report: ModuleType, monkeypatch: pytest.MonkeyPatch, *args: str) -> int:
    """Run the script's main() with the given arguments."""
    monkeypatch.setattr(sys, "argv", ["mutation_report.py", *args])
    return int(report.main())


def test_no_mutants_when_module_has_none(
    report: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A generated module without mutants counts as having nothing to mutate."""
    write_meta(SERVICES, {})
    assert report.has_no_mutants([SERVICES])
    assert run(report, monkeypatch, "--no-mutants", SERVICES) == 0


def test_mutants_present(report: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """A module with mutants, alone or next to an empty one, is not empty."""
    write_meta(SERVICES, {})
    write_meta(API, {"custom_components.omada_open_api.api.x_f__mutmut_1": None})
    assert not report.has_no_mutants([API])
    assert not report.has_no_mutants([SERVICES, API])
    assert run(report, monkeypatch, "--no-mutants", SERVICES, API) == 1


def test_not_generated(report: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a .meta file mutmut did not get as far as generating mutants."""
    assert not report.has_no_mutants([SERVICES])
    assert not report.has_no_mutants([])
    assert run(report, monkeypatch, "--no-mutants", SERVICES) == 1
