"""Sensor support for the FoxESS OpenAPI integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfReactivePower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.icon import icon_for_battery_level
from homeassistant.helpers.typing import StateType

from .const import (
    ATTR_BATTERY_LIST,
    ATTR_DEVICE_SN,
    ATTR_DEVICE_TYPE,
    ATTR_LAST_CLOUD_SYNC,
    ATTR_MANAGER_VERSION,
    ATTR_MASTER_VERSION,
    ATTR_MODULE_SN,
    ATTR_PLANT_NAME,
    ATTR_SLAVE_VERSION,
    RUNNING_STATE_MAP,
)
from .coordinator import FoxESSCoordinator, FoxESSData
from .entity import FoxESSEntity


@dataclass(frozen=True, kw_only=True)
class FoxESSSensorEntityDescription(SensorEntityDescription):
    """Describe a FoxESS sensor."""

    value_fn: Callable[[FoxESSData], StateType]
    available_fn: Callable[[FoxESSData], bool] = field(default=lambda _data: True)
    required_realtime_key: str | None = None


def _has_realtime(data: FoxESSData, key: str) -> bool:
    """Return whether realtime data contains a value."""
    return data.online and data.realtime.get(key) is not None


def _realtime_value(key: str) -> Callable[[FoxESSData], StateType]:
    """Return a realtime value function."""
    return lambda data: data.realtime.get(key) if _has_realtime(data, key) else None


def _report_value(key: str) -> Callable[[FoxESSData], StateType]:
    """Return a monthly report value function."""
    return lambda data: data.report.get(key)


def _generation_value(key: str) -> Callable[[FoxESSData], StateType]:
    """Return a generation report value function."""
    return lambda data: data.generation.get(key)


def _battery_value(key: str) -> Callable[[FoxESSData], StateType]:
    """Return a battery setting value function."""
    return lambda data: data.battery.get(key)


def _setting_value(key: str) -> Callable[[FoxESSData], StateType]:
    """Return a device setting value function."""
    return lambda data: (data.settings.get(key) or {}).get("value")


def _should_create_sensor(
    data: FoxESSData, description: FoxESSSensorEntityDescription
) -> bool:
    """Return whether a hardware-specific sensor should be created."""
    if description.required_realtime_key is None:
        return True
    return data.realtime.get(description.required_realtime_key) is not None


def _sum_power(data: FoxESSData) -> float:
    """Estimate generated solar power from instantaneous power flows."""
    loads = float(data.realtime.get("loadsPower") or 0)
    charge = float(data.realtime.get("batChargePower") or 0)
    feed_in = float(data.realtime.get("feedinPower") or 0)
    grid = float(data.realtime.get("gridConsumptionPower") or 0)
    discharge = float(data.realtime.get("batDischargePower") or 0)
    return round(max(loads + charge + feed_in - grid - discharge, 0), 3)


def _sum_energy(data: FoxESSData) -> float:
    """Estimate generated solar energy from daily energy flows."""
    loads = float(data.report.get("loads") or 0)
    charge = float(data.report.get("chargeEnergyToTal") or 0)
    feed_in = float(data.report.get("feedin") or 0)
    grid = float(data.report.get("gridConsumption") or 0)
    discharge = float(data.report.get("dischargeEnergyToTal") or 0)
    return round(max(loads + charge + feed_in - grid - discharge, 0), 3)


def _running_state(data: FoxESSData) -> str | None:
    """Return the FoxESS running state with its label."""
    value = data.realtime.get("runningState")
    if value is None:
        return None
    code = str(value)
    return f"{code}: {RUNNING_STATE_MAP.get(code, 'unknown')}"


def _reactive_power(data: FoxESSData) -> float | None:
    """Return reactive power in VAR."""
    value = data.realtime.get("ReactivePower")
    if value is None:
        return None
    return float(value) * 1000


def _residual_energy(data: FoxESSData) -> float | None:
    """Return residual battery energy in kWh."""
    value = data.realtime.get("ResidualEnergy")
    if value is None:
        return None
    residual = float(value)
    if residual > 50:
        residual = residual / 100
    return round(max(residual, 0), 3)


CORE_SENSOR_DESCRIPTIONS: tuple[FoxESSSensorEntityDescription, ...] = (
    FoxESSSensorEntityDescription(
        key="generation_power",
        name="Generation Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=_realtime_value("generationPower"),
    ),
    FoxESSSensorEntityDescription(
        key="grid_consumption_power",
        name="Grid Consumption Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=_realtime_value("gridConsumptionPower"),
    ),
    FoxESSSensorEntityDescription(
        key="feed_in_power",
        name="Feed-in Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=_realtime_value("feedinPower"),
    ),
    FoxESSSensorEntityDescription(
        key="battery_discharge_power",
        name="Battery Discharge Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=_realtime_value("batDischargePower"),
    ),
    FoxESSSensorEntityDescription(
        key="battery_charge_power",
        name="Battery Charge Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=_realtime_value("batChargePower"),
    ),
    FoxESSSensorEntityDescription(
        key="load_power",
        name="Load Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=_realtime_value("loadsPower"),
    ),
    FoxESSSensorEntityDescription(
        key="solar_power",
        name="Solar Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=_sum_power,
        available_fn=lambda data: data.online and bool(data.realtime),
    ),
    FoxESSSensorEntityDescription(
        key="inverter_battery_power",
        name="Inverter Battery Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=_realtime_value("invBatPower"),
    ),
    FoxESSSensorEntityDescription(
        key="inverter_battery_power_2",
        name="Inverter Battery Power 2",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=_realtime_value("invBatPower_2"),
        required_realtime_key="invBatPower_2",
    ),
    FoxESSSensorEntityDescription(
        key="meter_2_power",
        name="Meter 2 Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=_realtime_value("meterPower2"),
    ),
    FoxESSSensorEntityDescription(
        key="pv_power",
        name="PV Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=_realtime_value("pvPower"),
    ),
    FoxESSSensorEntityDescription(
        key="reactive_power",
        name="Reactive Power",
        device_class=SensorDeviceClass.REACTIVE_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfReactivePower.VOLT_AMPERE_REACTIVE,
        value_fn=_reactive_power,
        available_fn=lambda data: _has_realtime(data, "ReactivePower"),
    ),
    FoxESSSensorEntityDescription(
        key="power_factor",
        name="Power Factor",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=_realtime_value("PowerFactor"),
    ),
    FoxESSSensorEntityDescription(
        key="running_state",
        name="Running State",
        icon="mdi:state-machine",
        value_fn=_running_state,
        available_fn=lambda data: bool(data.realtime),
    ),
    FoxESSSensorEntityDescription(
        key="work_mode",
        name="Work Mode",
        icon="mdi:cog-transfer",
        value_fn=_setting_value("WorkMode"),
        available_fn=lambda data: (
            (data.settings.get("WorkMode") or {}).get("value") is not None
        ),
    ),
    FoxESSSensorEntityDescription(
        key="inverter_fault_code",
        name="Inverter Fault Code",
        icon="mdi:alert-circle-outline",
        value_fn=_realtime_value("currentFault"),
        available_fn=lambda data: _has_realtime(data, "currentFault"),
    ),
    FoxESSSensorEntityDescription(
        key="response_time",
        name="API Response Time",
        native_unit_of_measurement="ms",
        value_fn=lambda data: data.response_time_ms,
        available_fn=lambda data: data.response_time_ms is not None,
    ),
    FoxESSSensorEntityDescription(
        key="battery_soc",
        name="Battery SoC",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=_realtime_value("SoC"),
    ),
    FoxESSSensorEntityDescription(
        key="battery_soc_1",
        name="Battery SoC 1",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=_realtime_value("SoC_1"),
    ),
    FoxESSSensorEntityDescription(
        key="battery_soc_2",
        name="Battery SoC 2",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=_realtime_value("SoC_2"),
        required_realtime_key="SoC_2",
    ),
    FoxESSSensorEntityDescription(
        key="battery_soh",
        name="Battery SoH",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=_realtime_value("SOH"),
    ),
    FoxESSSensorEntityDescription(
        key="minimum_soc",
        name="Minimum SoC",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=_battery_value("minSoc"),
        available_fn=lambda data: data.battery.get("minSoc") is not None,
    ),
    FoxESSSensorEntityDescription(
        key="minimum_soc_on_grid",
        name="Minimum SoC on Grid",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=_battery_value("minSocOnGrid"),
        available_fn=lambda data: data.battery.get("minSocOnGrid") is not None,
    ),
    FoxESSSensorEntityDescription(
        key="energy_generated_today",
        name="Energy Generated Today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=_generation_value("today"),
    ),
    FoxESSSensorEntityDescription(
        key="energy_generated_month",
        name="Energy Generated Month",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=_generation_value("month"),
    ),
    FoxESSSensorEntityDescription(
        key="energy_generated_total",
        name="Energy Generated Total",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=_generation_value("cumulative"),
    ),
    FoxESSSensorEntityDescription(
        key="grid_consumption_energy",
        name="Grid Consumption Today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=_report_value("gridConsumption"),
    ),
    FoxESSSensorEntityDescription(
        key="feed_in_energy",
        name="Feed-in Today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=_report_value("feedin"),
    ),
    FoxESSSensorEntityDescription(
        key="battery_charge_energy",
        name="Battery Charge Today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=_report_value("chargeEnergyToTal"),
    ),
    FoxESSSensorEntityDescription(
        key="battery_discharge_energy",
        name="Battery Discharge Today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=_report_value("dischargeEnergyToTal"),
    ),
    FoxESSSensorEntityDescription(
        key="load_energy",
        name="Load",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=_report_value("loads"),
    ),
    FoxESSSensorEntityDescription(
        key="pv_energy_total",
        name="PV Energy Total",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=_report_value("PVEnergyTotal"),
    ),
    FoxESSSensorEntityDescription(
        key="solar_energy",
        name="Solar",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=_sum_energy,
        available_fn=lambda data: bool(data.report),
    ),
    FoxESSSensorEntityDescription(
        key="energy_throughput",
        name="Energy Throughput",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=_realtime_value("energyThroughput"),
    ),
    FoxESSSensorEntityDescription(
        key="residual_energy",
        name="Residual Energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=_residual_energy,
        available_fn=lambda data: _has_realtime(data, "ResidualEnergy"),
    ),
)

PHASE_SENSOR_DESCRIPTIONS: tuple[FoxESSSensorEntityDescription, ...] = tuple(
    description
    for phase in ("R", "S", "T")
    for description in (
        FoxESSSensorEntityDescription(
            key=f"{phase.lower()}_current",
            name=f"{phase} Current",
            device_class=SensorDeviceClass.CURRENT,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            value_fn=_realtime_value(f"{phase}Current"),
        ),
        FoxESSSensorEntityDescription(
            key=f"{phase.lower()}_frequency",
            name=f"{phase} Frequency",
            device_class=SensorDeviceClass.FREQUENCY,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfFrequency.HERTZ,
            value_fn=_realtime_value(f"{phase}Freq"),
        ),
        FoxESSSensorEntityDescription(
            key=f"{phase.lower()}_power",
            name=f"{phase} Power",
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfPower.KILO_WATT,
            value_fn=_realtime_value(f"{phase}Power"),
        ),
        FoxESSSensorEntityDescription(
            key=f"{phase.lower()}_voltage",
            name=f"{phase} Voltage",
            device_class=SensorDeviceClass.VOLTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfElectricPotential.VOLT,
            value_fn=_realtime_value(f"{phase}Volt"),
        ),
    )
)

TEMPERATURE_SENSOR_DESCRIPTIONS: tuple[FoxESSSensorEntityDescription, ...] = (
    FoxESSSensorEntityDescription(
        key="battery_temperature",
        name="Battery Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=_realtime_value("batTemperature"),
    ),
    FoxESSSensorEntityDescription(
        key="battery_temperature_2",
        name="Battery Temperature 2",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=_realtime_value("batTemperature_2"),
        required_realtime_key="batTemperature_2",
    ),
    FoxESSSensorEntityDescription(
        key="ambient_temperature",
        name="Ambient Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=_realtime_value("ambientTemperation"),
    ),
    FoxESSSensorEntityDescription(
        key="boost_temperature",
        name="Boost Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=_realtime_value("boostTemperation"),
    ),
    FoxESSSensorEntityDescription(
        key="inverter_temperature",
        name="Inverter Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=_realtime_value("invTemperation"),
    ),
)

BATTERY_CURRENT_DESCRIPTIONS: tuple[FoxESSSensorEntityDescription, ...] = (
    FoxESSSensorEntityDescription(
        key="max_battery_charge_current",
        name="Max Battery Charge Current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        value_fn=_realtime_value("maxChargeCurrent"),
    ),
    FoxESSSensorEntityDescription(
        key="max_battery_discharge_current",
        name="Max Battery Discharge Current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        value_fn=_realtime_value("maxDischargeCurrent"),
    ),
)


def _pv_sensor_descriptions(max_strings: int) -> list[FoxESSSensorEntityDescription]:
    """Return PV string sensor descriptions."""
    descriptions: list[FoxESSSensorEntityDescription] = []
    for string_number in range(1, max_strings + 1):
        prefix = f"pv{string_number}"
        name = f"PV{string_number}"
        descriptions.extend(
            [
                FoxESSSensorEntityDescription(
                    key=f"{prefix}_current",
                    name=f"{name} Current",
                    device_class=SensorDeviceClass.CURRENT,
                    state_class=SensorStateClass.MEASUREMENT,
                    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
                    value_fn=_realtime_value(f"{prefix}Current"),
                    required_realtime_key=f"{prefix}Current"
                    if string_number >= 5
                    else None,
                ),
                FoxESSSensorEntityDescription(
                    key=f"{prefix}_power",
                    name=f"{name} Power",
                    device_class=SensorDeviceClass.POWER,
                    state_class=SensorStateClass.MEASUREMENT,
                    native_unit_of_measurement=UnitOfPower.KILO_WATT,
                    value_fn=_realtime_value(f"{prefix}Power"),
                    required_realtime_key=f"{prefix}Power"
                    if string_number >= 5
                    else None,
                ),
                FoxESSSensorEntityDescription(
                    key=f"{prefix}_voltage",
                    name=f"{name} Voltage",
                    device_class=SensorDeviceClass.VOLTAGE,
                    state_class=SensorStateClass.MEASUREMENT,
                    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
                    value_fn=_realtime_value(f"{prefix}Volt"),
                    required_realtime_key=f"{prefix}Volt"
                    if string_number >= 5
                    else None,
                ),
            ]
        )
    return descriptions


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up FoxESS sensors from a config entry."""
    coordinator = entry.runtime_data

    descriptions = [
        *_pv_sensor_descriptions(coordinator.max_pv_strings),
        *CORE_SENSOR_DESCRIPTIONS,
        *PHASE_SENSOR_DESCRIPTIONS,
        *TEMPERATURE_SENSOR_DESCRIPTIONS,
        *BATTERY_CURRENT_DESCRIPTIONS,
    ]

    async_add_entities(
        [
            FoxESSDeviceStatusSensor(coordinator),
            *(
                FoxESSSensor(coordinator, description)
                for description in descriptions
                if _should_create_sensor(coordinator.data, description)
            ),
        ]
    )


class FoxESSDeviceStatusSensor(FoxESSEntity, SensorEntity):
    """Representation of the inverter status sensor."""

    _attr_icon = "mdi:solar-power"
    _attr_name = "Inverter"

    def __init__(self, coordinator: FoxESSCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.serial_number}_inverter"

    @property
    def native_value(self) -> str | None:
        """Return the inverter status."""
        return self.coordinator.device_status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return useful FoxESS device metadata."""
        data = self.coordinator.data
        device = data.device
        return {
            ATTR_DEVICE_SN: device.get(ATTR_DEVICE_SN),
            ATTR_PLANT_NAME: device.get(ATTR_PLANT_NAME) or device.get("stationName"),
            ATTR_MODULE_SN: device.get(ATTR_MODULE_SN),
            ATTR_DEVICE_TYPE: device.get(ATTR_DEVICE_TYPE),
            ATTR_MASTER_VERSION: device.get(ATTR_MASTER_VERSION),
            ATTR_MANAGER_VERSION: device.get(ATTR_MANAGER_VERSION),
            ATTR_SLAVE_VERSION: device.get(ATTR_SLAVE_VERSION),
            ATTR_BATTERY_LIST: device.get(ATTR_BATTERY_LIST),
            ATTR_LAST_CLOUD_SYNC: data.last_cloud_sync,
        }


class FoxESSSensor(FoxESSEntity, SensorEntity):
    """Representation of a FoxESS sensor."""

    entity_description: FoxESSSensorEntityDescription

    def __init__(
        self,
        coordinator: FoxESSCoordinator,
        description: FoxESSSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.serial_number}_{description.key}"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            super().available
            and self.coordinator.data is not None
            and self.entity_description.available_fn(self.coordinator.data)
        )

    @property
    def native_value(self) -> StateType:
        """Return the sensor state."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def icon(self) -> str | None:
        """Return battery-aware icons for battery percentage sensors."""
        if self.entity_description.device_class == SensorDeviceClass.BATTERY:
            value = self.native_value
            if isinstance(value, (int, float)):
                return icon_for_battery_level(battery_level=value, charging=None)
        return super().icon
