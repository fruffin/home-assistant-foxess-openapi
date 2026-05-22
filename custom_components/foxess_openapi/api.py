"""Async client for the FoxESS Open API."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import date
import hashlib
import logging
import time
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession, ClientTimeout

from .const import DEFAULT_API_HOST, DEFAULT_LANGUAGE, MIN_SECONDS_BETWEEN_REQUESTS

_LOGGER = logging.getLogger(__name__)

API_ERROR_AUTH_CODES = {41807, 41808, 41809}
API_ERROR_DEVICE_CODES = {40261, 41930}

PATH_BATTERY_SOC = "/op/v0/device/battery/soc/get"
PATH_DAILY_GENERATION = "/op/v0/device/generation"
PATH_DEVICE_DETAIL = "/op/v1/device/detail"
PATH_MONTHLY_REPORT = "/op/v0/device/report/query"
PATH_REALTIME = "/op/v1/device/real/query"

REPORT_VARIABLES = [
    "feedin",
    "generation",
    "gridConsumption",
    "chargeEnergyToTal",
    "dischargeEnergyToTal",
    "loads",
    "PVEnergyTotal",
]

REALTIME_VARIABLES = [
    "ambientTemperation",
    "batChargePower",
    "batCurrent",
    "batCurrent_1",
    "batCurrent_2",
    "batDischargePower",
    "batTemperature",
    "batTemperature_1",
    "batTemperature_2",
    "batVolt",
    "batVolt_1",
    "batVolt_2",
    "boostTemperation",
    "chargeTemperature",
    "dspTemperature",
    "epsCurrentR",
    "epsCurrentS",
    "epsCurrentT",
    "epsPower",
    "epsPowerR",
    "epsPowerS",
    "epsPowerT",
    "epsVoltR",
    "epsVoltS",
    "epsVoltT",
    "energyThroughput",
    "feedinPower",
    "generationPower",
    "gridConsumptionPower",
    "input",
    "invBatCurrent",
    "invBatPower",
    "invBatPower_1",
    "invBatPower_2",
    "invBatVolt",
    "invTemperation",
    "loadsPower",
    "loadsPowerR",
    "loadsPowerS",
    "loadsPowerT",
    "maxChargeCurrent",
    "maxDischargeCurrent",
    "meterPower",
    "meterPower2",
    "meterPowerR",
    "meterPowerS",
    "meterPowerT",
    "PowerFactor",
    "pvPower",
    "RCurrent",
    "ReactivePower",
    "RFreq",
    "RPower",
    "RVolt",
    "ResidualEnergy",
    "runningState",
    "currentFaultCount",
    "SCurrent",
    "SFreq",
    "SoC",
    "SoC_1",
    "SoC_2",
    "SOH",
    "SPower",
    "SVolt",
    "TCurrent",
    "TFreq",
    "TPower",
    "TVolt",
]

PV_VARIABLES = [
    variable
    for string_number in range(1, 19)
    for variable in (
        f"pv{string_number}Current",
        f"pv{string_number}Power",
        f"pv{string_number}Volt",
    )
]


class FoxESSApiError(Exception):
    """Base exception for FoxESS API errors."""


class FoxESSAuthError(FoxESSApiError):
    """Raised when FoxESS rejects the API key."""


class FoxESSDeviceNotFoundError(FoxESSApiError):
    """Raised when FoxESS rejects the configured device serial number."""


class FoxESSCannotConnectError(FoxESSApiError):
    """Raised when FoxESS cannot be reached."""


class FoxESSOpenApi:
    """Client for the FoxESS Open API."""

    def __init__(
        self,
        session: ClientSession,
        api_key: str,
        *,
        host: str = DEFAULT_API_HOST,
        language: str = DEFAULT_LANGUAGE,
    ) -> None:
        """Initialize the API client."""
        self._session = session
        self._api_key = api_key
        self._host = host.rstrip("/")
        self._language = language
        self._lock = asyncio.Lock()
        self._last_request = 0.0
        self.last_response_time_ms: int | None = None

    async def get_device_detail(self, serial_number: str) -> dict[str, Any]:
        """Return device metadata for a serial number."""
        result = await self._request(
            "GET",
            PATH_DEVICE_DETAIL,
            params={"sn": serial_number},
        )
        if not isinstance(result, dict):
            raise FoxESSApiError("Unexpected device detail response")
        return result

    async def get_realtime_data(
        self, serial_number: str, max_pv_strings: int
    ) -> dict[str, Any]:
        """Return realtime variables keyed by FoxESS variable name."""
        result = await self._request(
            "POST",
            PATH_REALTIME,
            json={
                "sns": [serial_number],
                "variables": [
                    *REALTIME_VARIABLES,
                    *PV_VARIABLES[: max_pv_strings * 3],
                ],
            },
        )

        if not isinstance(result, list) or not result:
            return {}

        device_result = self._find_serial_result(result, serial_number)
        datas = device_result.get("datas", [])
        values: dict[str, Any] = {}
        for item in datas:
            variable = item.get("variable")
            if not variable:
                continue
            value = item.get("value")
            values[variable] = self._normalize_realtime_value(variable, value, item)

        if "batTemperature_1" in values and "batTemperature" not in values:
            values["batTemperature"] = values["batTemperature_1"]
        if "invBatPower_1" in values and "invBatPower" not in values:
            values["invBatPower"] = values["invBatPower_1"]

        received_time = device_result.get("time")
        if received_time:
            values["_received_time"] = received_time

        return values

    async def get_battery_soc(self, serial_number: str) -> dict[str, Any]:
        """Return battery state-of-charge settings."""
        result = await self._request(
            "GET",
            PATH_BATTERY_SOC,
            params={"sn": serial_number},
        )
        if not isinstance(result, dict):
            return {}
        return result

    async def get_daily_generation(self, serial_number: str) -> dict[str, Any]:
        """Return daily/monthly/cumulative generation data."""
        result = await self._request(
            "GET",
            PATH_DAILY_GENERATION,
            params={"sn": serial_number},
        )
        if not isinstance(result, dict):
            return {}
        return {
            "today": result.get("today", 0),
            "month": result.get("month", 0),
            "cumulative": result.get("cumulative", 0),
        }

    async def get_monthly_report(
        self, serial_number: str, report_date: date
    ) -> dict[str, float]:
        """Return today's totals from the current monthly report."""
        result = await self._request(
            "POST",
            PATH_MONTHLY_REPORT,
            json={
                "sn": serial_number,
                "year": report_date.year,
                "month": report_date.month,
                "dimension": "month",
                "variables": REPORT_VARIABLES,
            },
        )

        if not isinstance(result, list):
            return {}

        report: dict[str, float] = {}
        day_index = report_date.day - 1
        for item in result:
            variable = item.get("variable")
            values = item.get("values") or []
            if not variable or len(values) <= day_index:
                continue
            value = values[day_index]
            if value is not None:
                report[variable] = round(float(value), 3)

        return report

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
    ) -> Any:
        """Make an authenticated FoxESS API request."""
        await self._rate_limit()

        headers = self._auth_headers(path)
        url = f"{self._host}{path}"
        started = time.monotonic()

        try:
            async with self._session.request(
                method,
                url,
                params=params,
                json=json,
                headers=headers,
                timeout=ClientTimeout(total=75),
            ) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
        except ClientResponseError as err:
            raise FoxESSCannotConnectError(
                f"FoxESS returned HTTP {err.status}"
            ) from err
        except (ClientError, TimeoutError, asyncio.TimeoutError) as err:
            raise FoxESSCannotConnectError("Unable to reach FoxESS Open API") from err
        except ValueError as err:
            raise FoxESSCannotConnectError(
                "FoxESS returned an invalid response"
            ) from err

        self.last_response_time_ms = round((time.monotonic() - started) * 1000)

        if not isinstance(payload, dict):
            raise FoxESSApiError("FoxESS returned an unexpected response")

        errno = payload.get("errno")
        if errno == 0:
            return payload.get("result")

        message = payload.get("msg") or payload.get("message") or "unknown error"
        _LOGGER.debug("FoxESS API error %s for %s: %s", errno, path, payload)

        if errno in API_ERROR_AUTH_CODES:
            raise FoxESSAuthError(message)
        if errno in API_ERROR_DEVICE_CODES:
            raise FoxESSDeviceNotFoundError(message)
        raise FoxESSApiError(f"FoxESS API error {errno}: {message}")

    async def _rate_limit(self) -> None:
        """Enforce FoxESS' minimum delay between Open API requests."""
        async with self._lock:
            elapsed = time.monotonic() - self._last_request
            delay = MIN_SECONDS_BETWEEN_REQUESTS - elapsed
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request = time.monotonic()

    def _auth_headers(self, path: str) -> dict[str, str]:
        """Return FoxESS Open API authentication headers."""
        timestamp = str(round(time.time() * 1000))
        signature = hashlib.md5(  # noqa: S324 - required by FoxESS Open API
            rf"{path}\r\n{self._api_key}\r\n{timestamp}".encode("utf-8")
        ).hexdigest()

        return {
            "token": self._api_key,
            "lang": self._language,
            "timestamp": timestamp,
            "Content-Type": "application/json",
            "signature": signature,
            "User-Agent": "Home Assistant FoxESS OpenAPI",
        }

    @staticmethod
    def _find_serial_result(
        results: list[dict[str, Any]], serial_number: str
    ) -> dict[str, Any]:
        """Find the response for a serial number, falling back to the first result."""
        for item in results:
            if item.get("sn") == serial_number or item.get("deviceSN") == serial_number:
                return item
        return results[0]

    @staticmethod
    def _normalize_realtime_value(
        variable: str, value: Any, item: Mapping[str, Any]
    ) -> Any:
        """Normalize known FoxESS value quirks."""
        if value is None:
            return None

        if variable == "ResidualEnergy":
            unit = item.get("unit")
            if unit in {"1.0kWh", "kWh", None}:
                return round(float(value) * 100, 2)
            if unit == "0.1kWh":
                return round(float(value) * 10, 2)

        return value
