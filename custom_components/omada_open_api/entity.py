"""Base entity for the Omada Open API integration."""

from __future__ import annotations

from typing import TypeVar

from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

_CoordinatorT = TypeVar("_CoordinatorT", bound=DataUpdateCoordinator)


class OmadaEntity(CoordinatorEntity[_CoordinatorT]):  # type: ignore[misc]
    """Base entity for all Omada Open API entities.

    Provides shared defaults that apply to every entity in the integration.
    """

    _attr_has_entity_name = True
