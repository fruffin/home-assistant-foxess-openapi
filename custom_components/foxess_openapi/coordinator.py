"""Coordinator for the FoxESS OpenAPI integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import FoxESSApiError, FoxESSOpenApi
from .const import (
    ATTR_BATTERY_LIST,
    ATTR_DEVICE_SN,
    ATTR_MANAGER_VERSION,
    ATTR_MASTER_VERSION,
    ATTR_MODULE_SN,
    ATTR_SLAVE_VERSION,
    CONF_EXTENDED_PV,
    CONF_GENERATION_REFRESH_INTERVAL,
    CONF_REALTIME_REFRESH_INTERVAL,
    CONF_REPORT_REFRESH_INTERVAL,
    DEFAULT_GENERATION_REFRESH_INTERVAL,
    DEFAULT_REALTIME_REFRESH_INTERVAL,
    DEFAULT_REPORT_REFRESH_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DEVICE_STATUS_MAP,
    DOMAIN,
    MAX_REFRESH_INTERVAL,
    MIN_REFRESH_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class FoxESSData:
    """Latest FoxESS data snapshot."""

    device: dict[str, Any] = field(default_factory=dict)
    realtime: dict[str, Any] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)
    report: dict[str, Any] = field(default_factory=dict)
    generation: dict[str, Any] = field(default_factory=dict)
    battery: dict[str, Any] = field(default_factory=dict)
    online: bool = False
    response_time_ms: int | None = None
    last_cloud_sync: datetime | None = None


class FoxESSCoordinator(DataUpdateCoordinator[FoxESSData]):
    """Manage FoxESS data refreshes."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: FoxESSOpenApi,
        serial_number: str,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{serial_number}",
            update_interval=DEFAULT_UPDATE_INTERVAL,
        )
        self.api = api
        self.serial_number = serial_number
        self.max_pv_strings = (
            18
            if entry.options.get(
                CONF_EXTENDED_PV, entry.data.get(CONF_EXTENDED_PV, False)
            )
            else 6
        )
        self._last_data = FoxESSData()
        self._force_full_refresh = False
        self._last_realtime_refresh: datetime | None = None
        self._last_report_refresh: datetime | None = None
        self._last_generation_refresh: datetime | None = None
        self._realtime_refresh_interval = self._entry_interval(
            CONF_REALTIME_REFRESH_INTERVAL, DEFAULT_REALTIME_REFRESH_INTERVAL
        )
        self._report_refresh_interval = self._entry_interval(
            CONF_REPORT_REFRESH_INTERVAL, DEFAULT_REPORT_REFRESH_INTERVAL
        )
        self._generation_refresh_interval = self._entry_interval(
            CONF_GENERATION_REFRESH_INTERVAL, DEFAULT_GENERATION_REFRESH_INTERVAL
        )
        self._update_coordinator_interval()

    async def _async_update_data(self) -> FoxESSData:
        """Fetch data from the FoxESS Open API."""
        now = dt_util.utcnow()
        force_refresh = self._force_full_refresh
        self._force_full_refresh = False
        first_refresh = self._last_data.last_cloud_sync is None
        report_refresh_due = (
            force_refresh or first_refresh or self._report_refresh_due(now)
        )
        generation_refresh_due = (
            force_refresh or first_refresh or self._generation_refresh_due(now)
        )

        data = FoxESSData(
            device=dict(self._last_data.device),
            realtime=dict(self._last_data.realtime),
            settings=dict(self._last_data.settings),
            report=dict(self._last_data.report),
            generation=dict(self._last_data.generation),
            battery=dict(self._last_data.battery),
            response_time_ms=self._last_data.response_time_ms,
            last_cloud_sync=self._last_data.last_cloud_sync,
        )
        refreshed = False

        try:
            if report_refresh_due:
                data.device = await self.api.get_device_detail(self.serial_number)
                refreshed = True

            data.online = self._device_is_online(data.device)

            if data.online and (
                force_refresh or first_refresh or self._realtime_refresh_due(now)
            ):
                data.realtime = await self.api.get_realtime_data(
                    self.serial_number,
                    self.max_pv_strings,
                )
                try:
                    data.settings["WorkMode"] = await self.api.get_device_setting(
                        self.serial_number,
                        "WorkMode",
                    )
                except FoxESSApiError as err:
                    _LOGGER.debug("Unable to fetch FoxESS WorkMode setting: %s", err)
                    data.settings.pop("WorkMode", None)
                self._last_realtime_refresh = now
                refreshed = True
            elif not data.online:
                data.realtime = {}
                data.settings = {}

            if report_refresh_due:
                data.report = await self.api.get_monthly_report(
                    self.serial_number, dt_util.now().date()
                )
                self._last_report_refresh = now
                refreshed = True

            if generation_refresh_due:
                data.generation = await self.api.get_daily_generation(
                    self.serial_number
                )
                if self._device_has_battery(data.device):
                    data.battery = await self.api.get_battery_soc(self.serial_number)
                else:
                    data.battery = {}
                self._last_generation_refresh = now
                refreshed = True

            data.response_time_ms = self.api.last_response_time_ms
            if refreshed:
                data.last_cloud_sync = now
        except FoxESSApiError as err:
            raise UpdateFailed(str(err)) from err

        self._last_data = data
        self._update_device_registry(data)
        return data

    @staticmethod
    def _device_is_online(device: dict[str, Any]) -> bool:
        """Return whether the inverter should be treated as online."""
        try:
            status = int(device.get("status"))
        except (TypeError, ValueError):
            return False
        return status in {1, 2}

    @staticmethod
    def _device_has_battery(device: dict[str, Any]) -> bool:
        """Return whether FoxESS reports a battery for the device."""
        if "hasBattery" in device:
            return bool(device["hasBattery"])
        battery_list = device.get(ATTR_BATTERY_LIST)
        return bool(battery_list and battery_list != "No Battery")

    def _update_device_registry(self, data: FoxESSData) -> None:
        """Keep serial-number device metadata fresh in the device registry."""
        device_registry = dr.async_get(self.hass)
        sw_versions = [
            data.device.get(ATTR_MASTER_VERSION),
            data.device.get(ATTR_MANAGER_VERSION),
            data.device.get(ATTR_SLAVE_VERSION),
        ]
        sw_version = " / ".join(str(version) for version in sw_versions if version)

        device_registry.async_get_or_create(
            config_entry_id=self.config_entry.entry_id,
            identifiers={(DOMAIN, self.serial_number)},
            manufacturer="FoxESS",
            model=data.device.get("deviceType"),
            name=data.device.get("stationName") or data.device.get("plantName"),
            serial_number=data.device.get(ATTR_DEVICE_SN) or self.serial_number,
            sw_version=sw_version or None,
            hw_version=data.device.get(ATTR_MODULE_SN),
        )

    @property
    def device_status(self) -> str | None:
        """Return the normalized device status."""
        try:
            status = int(self.data.device.get("status")) if self.data else None
        except (TypeError, ValueError):
            return None
        return DEVICE_STATUS_MAP.get(status)

    async def async_force_refresh(self) -> None:
        """Force all FoxESS datasets to refresh immediately."""
        self._force_full_refresh = True
        await self.async_request_refresh()

    def set_refresh_interval(self, key: str, minutes: int) -> None:
        """Set a refresh interval in minutes."""
        if key == CONF_REALTIME_REFRESH_INTERVAL:
            self._realtime_refresh_interval = minutes
        elif key == CONF_REPORT_REFRESH_INTERVAL:
            self._report_refresh_interval = minutes
        elif key == CONF_GENERATION_REFRESH_INTERVAL:
            self._generation_refresh_interval = minutes
        else:
            raise ValueError(f"Unsupported refresh interval key: {key}")

        self._update_coordinator_interval()

    def get_refresh_interval(self, key: str) -> int:
        """Return a refresh interval in minutes."""
        if key == CONF_REALTIME_REFRESH_INTERVAL:
            return self._realtime_refresh_interval
        if key == CONF_REPORT_REFRESH_INTERVAL:
            return self._report_refresh_interval
        if key == CONF_GENERATION_REFRESH_INTERVAL:
            return self._generation_refresh_interval
        raise ValueError(f"Unsupported refresh interval key: {key}")

    def _entry_interval(self, key: str, default: int) -> int:
        """Return a refresh interval from config entry options."""
        value = self.config_entry.options.get(
            key, self.config_entry.data.get(key, default)
        )
        try:
            minutes = int(value)
        except (TypeError, ValueError):
            return default
        return max(MIN_REFRESH_INTERVAL, min(MAX_REFRESH_INTERVAL, minutes))

    def _update_coordinator_interval(self) -> None:
        """Set the coordinator tick to the shortest configured interval."""
        self.update_interval = timedelta(
            minutes=min(
                self._realtime_refresh_interval,
                self._report_refresh_interval,
                self._generation_refresh_interval,
            )
        )

    def _realtime_refresh_due(self, now: datetime) -> bool:
        """Return whether realtime variables should be fetched."""
        return self._refresh_due(
            self._last_realtime_refresh, self._realtime_refresh_interval, now
        )

    def _report_refresh_due(self, now: datetime) -> bool:
        """Return whether device/report data should be fetched."""
        return self._refresh_due(
            self._last_report_refresh, self._report_refresh_interval, now
        )

    def _generation_refresh_due(self, now: datetime) -> bool:
        """Return whether generation/battery settings should be fetched."""
        return self._refresh_due(
            self._last_generation_refresh, self._generation_refresh_interval, now
        )

    @staticmethod
    def _refresh_due(
        last_refresh: datetime | None, interval_minutes: int, now: datetime
    ) -> bool:
        """Return whether a refresh interval has elapsed."""
        if last_refresh is None:
            return True
        return now - last_refresh >= timedelta(minutes=interval_minutes)
