"""Constants for the FoxESS OpenAPI integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "foxess_openapi"

PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.NUMBER, Platform.SENSOR]

DEFAULT_NAME = "FoxESS"
DEFAULT_API_HOST = "https://www.foxesscloud.com"
DEFAULT_LANGUAGE = "en"
DEFAULT_REALTIME_REFRESH_INTERVAL = 5
DEFAULT_REPORT_REFRESH_INTERVAL = 15
DEFAULT_GENERATION_REFRESH_INTERVAL = 60
DEFAULT_UPDATE_INTERVAL = timedelta(minutes=DEFAULT_REALTIME_REFRESH_INTERVAL)

CONF_API_KEY = "api_key"
CONF_DEVICE_SN = "device_sn"
CONF_EXTENDED_PV = "extended_pv"
CONF_GENERATION_REFRESH_INTERVAL = "generation_refresh_interval"
CONF_REALTIME_REFRESH_INTERVAL = "realtime_refresh_interval"
CONF_REPORT_REFRESH_INTERVAL = "report_refresh_interval"

MIN_SECONDS_BETWEEN_REQUESTS = 1.05
MIN_REFRESH_INTERVAL = 5
MAX_REFRESH_INTERVAL = 1440

ATTR_BATTERY_LIST = "batteryList"
ATTR_DEVICE_SN = "deviceSN"
ATTR_DEVICE_TYPE = "deviceType"
ATTR_LAST_CLOUD_SYNC = "lastCloudSync"
ATTR_MANAGER_VERSION = "managerVersion"
ATTR_MASTER_VERSION = "masterVersion"
ATTR_MODULE_SN = "moduleSN"
ATTR_PLANT_NAME = "plantName"
ATTR_SLAVE_VERSION = "slaveVersion"
ATTR_STATION_NAME = "stationName"

RUNNING_STATE_MAP = {
    "160": "self-test",
    "161": "waiting",
    "162": "checking",
    "163": "on-grid",
    "164": "off-grid",
    "165": "fault",
    "166": "permanent-fault",
    "167": "standby",
    "168": "upgrading",
    "169": "fct",
    "170": "illegal",
}

DEVICE_STATUS_MAP = {
    1: "online",
    2: "in alarm",
    3: "offline",
}
