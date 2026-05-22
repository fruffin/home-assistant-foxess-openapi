"""Number entities for the FoxESS OpenAPI integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from .const import (
    CONF_GENERATION_REFRESH_INTERVAL,
    CONF_REALTIME_REFRESH_INTERVAL,
    CONF_REPORT_REFRESH_INTERVAL,
    DEFAULT_GENERATION_REFRESH_INTERVAL,
    DEFAULT_REALTIME_REFRESH_INTERVAL,
    DEFAULT_REPORT_REFRESH_INTERVAL,
    MAX_REFRESH_INTERVAL,
    MIN_REFRESH_INTERVAL,
)
from .coordinator import FoxESSCoordinator
from .entity import FoxESSEntity


@dataclass(frozen=True, kw_only=True)
class FoxESSRefreshIntervalEntityDescription(NumberEntityDescription):
    """Describe a FoxESS refresh interval number entity."""

    default_value: int


REFRESH_INTERVAL_DESCRIPTIONS: tuple[FoxESSRefreshIntervalEntityDescription, ...] = (
    FoxESSRefreshIntervalEntityDescription(
        key=CONF_REALTIME_REFRESH_INTERVAL,
        name="Realtime Refresh Interval",
        default_value=DEFAULT_REALTIME_REFRESH_INTERVAL,
    ),
    FoxESSRefreshIntervalEntityDescription(
        key=CONF_REPORT_REFRESH_INTERVAL,
        name="Device and Report Refresh Interval",
        default_value=DEFAULT_REPORT_REFRESH_INTERVAL,
    ),
    FoxESSRefreshIntervalEntityDescription(
        key=CONF_GENERATION_REFRESH_INTERVAL,
        name="Generation and Battery Refresh Interval",
        default_value=DEFAULT_GENERATION_REFRESH_INTERVAL,
    ),
)


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up FoxESS number entities from a config entry."""
    coordinator = entry.runtime_data

    async_add_entities(
        FoxESSRefreshIntervalNumber(coordinator, description)
        for description in REFRESH_INTERVAL_DESCRIPTIONS
    )


class FoxESSRefreshIntervalNumber(FoxESSEntity, NumberEntity):
    """Representation of a configurable FoxESS refresh interval."""

    entity_description: FoxESSRefreshIntervalEntityDescription

    _attr_device_class = NumberDeviceClass.DURATION
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:timer-cog"
    _attr_mode = NumberMode.BOX
    _attr_native_max_value = MAX_REFRESH_INTERVAL
    _attr_native_min_value = MIN_REFRESH_INTERVAL
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(
        self,
        coordinator: FoxESSCoordinator,
        description: FoxESSRefreshIntervalEntityDescription,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.serial_number}_{description.key}"

    @property
    def native_value(self) -> float:
        """Return the current interval."""
        return self.coordinator.get_refresh_interval(self.entity_description.key)

    async def async_set_native_value(self, value: float) -> None:
        """Set the refresh interval."""
        minutes = max(
            MIN_REFRESH_INTERVAL,
            min(MAX_REFRESH_INTERVAL, round(value)),
        )
        self.coordinator.set_refresh_interval(self.entity_description.key, minutes)

        entry = self.coordinator.config_entry
        self.hass.config_entries.async_update_entry(
            entry,
            options={**entry.options, self.entity_description.key: minutes},
        )
        self.async_write_ha_state()
