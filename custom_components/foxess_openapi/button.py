"""Button entities for the FoxESS OpenAPI integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import FoxESSCoordinator
from .entity import FoxESSEntity


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up FoxESS button entities from a config entry."""
    async_add_entities([FoxESSForceRefreshButton(entry.runtime_data)])


class FoxESSForceRefreshButton(FoxESSEntity, ButtonEntity):
    """Button to force a FoxESS API refresh."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:refresh"
    _attr_name = "Force Refresh"

    def __init__(self, coordinator: FoxESSCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.serial_number}_force_refresh"

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.async_force_refresh()
