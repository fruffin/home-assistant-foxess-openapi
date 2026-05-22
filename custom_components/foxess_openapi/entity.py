"""Base entities for the FoxESS OpenAPI integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_DEVICE_SN,
    ATTR_DEVICE_TYPE,
    ATTR_MANAGER_VERSION,
    ATTR_MASTER_VERSION,
    ATTR_MODULE_SN,
    ATTR_PLANT_NAME,
    ATTR_SLAVE_VERSION,
    ATTR_STATION_NAME,
    DOMAIN,
)
from .coordinator import FoxESSCoordinator


class FoxESSEntity(CoordinatorEntity[FoxESSCoordinator]):
    """Base FoxESS entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FoxESSCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_device_info = self._device_info()

    def _device_info(self) -> DeviceInfo:
        """Return Home Assistant device metadata."""
        device = self.coordinator.data.device if self.coordinator.data else {}
        sw_versions = [
            device.get(ATTR_MASTER_VERSION),
            device.get(ATTR_MANAGER_VERSION),
            device.get(ATTR_SLAVE_VERSION),
        ]
        sw_version = " / ".join(str(version) for version in sw_versions if version)

        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.serial_number)},
            manufacturer="FoxESS",
            model=device.get(ATTR_DEVICE_TYPE),
            name=device.get(ATTR_STATION_NAME)
            or device.get(ATTR_PLANT_NAME)
            or self.coordinator.config_entry.title,
            serial_number=device.get(ATTR_DEVICE_SN) or self.coordinator.serial_number,
            sw_version=sw_version or None,
            hw_version=device.get(ATTR_MODULE_SN),
        )
