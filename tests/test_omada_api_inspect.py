"""Tests for the developer script scripts/omada_api_inspect.py (TLS validation)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "omada_api_inspect.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("omada_api_inspect", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _token_session() -> MagicMock:
    response = AsyncMock()
    response.json.return_value = {
        "errorCode": 0,
        "result": {"accessToken": "token"},
    }
    session = MagicMock()
    session.post.return_value.__aenter__.return_value = response
    return session


async def test_get_token_validates_certificates_by_default() -> None:
    """The token request keeps aiohttp's certificate validation on."""
    script = _load_script()
    session = _token_session()

    token = await script._get_token(
        session, "https://controller", "omadac", "client", "secret"
    )

    assert token == "token"
    assert session.post.call_args.kwargs["ssl"] is True


async def test_get_token_insecure_opt_out() -> None:
    """verify_ssl=False disables validation for self-signed controllers."""
    script = _load_script()
    session = _token_session()

    await script._get_token(
        session,
        "https://controller",
        "omadac",
        "client",
        "secret",
        verify_ssl=False,
    )

    assert session.post.call_args.kwargs["ssl"] is False


@pytest.mark.parametrize(
    ("extra_args", "expected_verify"),
    [([], True), (["--insecure"], False)],
)
def test_main_passes_insecure_flag(
    extra_args: list[str], expected_verify: bool
) -> None:
    """Only --insecure turns certificate validation off."""
    script = _load_script()
    fetch = MagicMock(return_value=None)

    with (
        patch.object(sys, "argv", ["omada_api_inspect.py", "sites", *extra_args]),
        patch.object(script, "_fetch", fetch),
        patch.object(script.asyncio, "run"),
    ):
        script.main()

    assert fetch.call_args.kwargs["verify_ssl"] is expected_verify
