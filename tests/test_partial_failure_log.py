"""Non-critical fetch failures warn once (quality scale: log-when-unavailable)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.omada_open_api.api import OmadaApiError
from custom_components.omada_open_api.coordinator import (
    OmadaSiteCoordinator,
    PartialFailureLog,
)

from .conftest import TEST_SITE_ID, TEST_SITE_NAME

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

GATEWAY_MAC = "AA-BB-CC-DD-EE-FF"


def _levels(caplog: pytest.LogCaptureFixture) -> list[int]:
    return [r.levelno for r in caplog.records if r.levelno >= logging.INFO]


def test_warns_once_then_logs_recovery(caplog: pytest.LogCaptureFixture) -> None:
    """Repeated failures warn once; recovery is logged once at info level."""
    caplog.set_level(logging.DEBUG)
    log = PartialFailureLog("Home")

    log.failed("PoE info", "Failed to fetch PoE info: %s", "boom")
    log.failed("PoE info", "Failed to fetch PoE info: %s", "boom")
    log.ok("PoE info")
    log.ok("PoE info")

    assert _levels(caplog) == [logging.WARNING, logging.INFO]


def test_keys_are_independent(caplog: pytest.LogCaptureFixture) -> None:
    """Each fetch key warns on its own first failure."""
    log = PartialFailureLog("Home")

    log.failed("a", "Failed a")
    log.failed("b", "Failed b")

    assert _levels(caplog) == [logging.WARNING, logging.WARNING]


async def test_wan_status_failure_warns_once_per_gateway(
    hass: HomeAssistant,
    mock_api_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A gateway whose WAN status keeps failing does not warn on every poll."""
    mock_api_client.get_gateway_wan_status = AsyncMock(
        side_effect=OmadaApiError("boom")
    )
    coordinator = OmadaSiteCoordinator(
        hass=hass,
        api_client=mock_api_client,
        site_id=TEST_SITE_ID,
        site_name=TEST_SITE_NAME,
    )
    devices = {GATEWAY_MAC: {"type": "gateway"}}

    for _ in range(3):
        await coordinator._fetch_wan_status(devices)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
