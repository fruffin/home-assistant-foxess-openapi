"""The FoxESS OpenAPI integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FoxESSOpenApi
from .const import CONF_API_KEY, CONF_DEVICE_SN, DEFAULT_API_HOST, PLATFORMS
from .coordinator import FoxESSCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up FoxESS OpenAPI from a config entry."""
    api = FoxESSOpenApi(
        async_get_clientsession(hass),
        entry.data[CONF_API_KEY],
        host=entry.data.get(CONF_HOST, DEFAULT_API_HOST),
    )

    coordinator = FoxESSCoordinator(
        hass,
        entry,
        api,
        entry.data[CONF_DEVICE_SN],
    )
    await coordinator.async_config_entry_first_refresh()

    station_name = coordinator.data.device.get(
        "stationName"
    ) or coordinator.data.device.get("plantName")
    if station_name and station_name != entry.title:
        hass.config_entries.async_update_entry(entry, title=station_name)

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
