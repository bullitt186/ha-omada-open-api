"""Fixtures for Omada Open API tests."""

from collections.abc import Generator

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: Generator,
) -> Generator:
    """Enable custom integrations for all tests."""
    return
