from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    DEGREE,
    PERCENTAGE,
    UnitOfIrradiance,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfVolumetricFlux,
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    UV_INDEX,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN, IMS_CITIES, ims_site_url
from .coordinator import ImsWeathercloudCoordinator


@dataclass(frozen=True, kw_only=True)
class MergedSensorDescription(SensorEntityDescription):
    source_key: str
    default: float | None = None  # value to show when the source reports nothing


SENSORS: tuple[MergedSensorDescription, ...] = (
    MergedSensorDescription(
        key="temperature", source_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:thermometer",
    ),
    MergedSensorDescription(
        key="apparent_temperature", source_key="apparent_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:thermometer-lines",
    ),
    MergedSensorDescription(
        key="humidity", source_key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:water-percent",
    ),
    MergedSensorDescription(
        key="wind_speed", source_key="wind_speed",
        device_class=SensorDeviceClass.WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:weather-windy",
    ),
    MergedSensorDescription(
        key="wind_speed_avg", source_key="wind_speed_avg",
        device_class=SensorDeviceClass.WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:weather-windy-variant",
    ),
    MergedSensorDescription(
        key="wind_gust", source_key="wind_gust",
        device_class=SensorDeviceClass.WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:weather-dust",
    ),
    MergedSensorDescription(
        key="wind_bearing", source_key="wind_bearing",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:compass-outline",
    ),
    MergedSensorDescription(
        key="wind_bearing_avg", source_key="wind_bearing_avg",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:compass",
    ),
    MergedSensorDescription(
        key="pressure", source_key="pressure",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        native_unit_of_measurement=UnitOfPressure.HPA,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:gauge",
    ),
    MergedSensorDescription(
        key="rain", source_key="rain",
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:weather-rainy",
    ),
    MergedSensorDescription(
        key="rain_rate", source_key="rain_rate",
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        native_unit_of_measurement=UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:weather-pouring",
        default=0.0, suggested_display_precision=1,
    ),
    MergedSensorDescription(
        key="precipitation_probability", source_key="precipitation_probability",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:cloud-percent",
    ),
    MergedSensorDescription(
        key="uv_index", source_key="uv_index",
        native_unit_of_measurement=UV_INDEX,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:weather-sunny-alert",
    ),
    MergedSensorDescription(
        key="dew_point", source_key="dew_point",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:water-thermometer",
    ),
    MergedSensorDescription(
        key="pm10", source_key="pm10",
        device_class=SensorDeviceClass.PM10,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:air-filter",
    ),
    MergedSensorDescription(
        key="solar_radiation", source_key="solar_radiation",
        device_class=SensorDeviceClass.IRRADIANCE,
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:solar-power",
        default=0.0, suggested_display_precision=1,
    ),
    MergedSensorDescription(
        key="inside_temperature", source_key="inside_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False, icon="mdi:home-thermometer",
    ),
    MergedSensorDescription(
        key="inside_humidity", source_key="inside_humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False, icon="mdi:home-percent",
    ),
)


def _device_info(entry: ConfigEntry, coordinator: ImsWeathercloudCoordinator) -> dict[str, Any]:
    name = (
        getattr(coordinator.data, "location_name", None)
        or IMS_CITIES.get(str(entry.data.get("city")), DEFAULT_NAME)
    )
    url = getattr(coordinator.data, "station_url", None) or ims_site_url(
        entry.data.get("language")
    )
    return {
        "identifiers": {(DOMAIN, entry.entry_id)},
        "name": name,
        "manufacturer": "IMS + Weathercloud",
        "entry_type": "service",
        "configuration_url": url,
    }


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: ImsWeathercloudCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        MergedSensor(coordinator, entry, desc) for desc in SENSORS
    ]
    entities.append(LocalitySensor(coordinator, entry))
    entities.append(CurrentConditionSensor(coordinator, entry))
    entities.append(ImsLastUpdateSensor(coordinator, entry))
    entities.append(WcLastUpdateSensor(coordinator, entry))
    async_add_entities(entities)


class _Base(CoordinatorEntity[ImsWeathercloudCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = _device_info(entry, coordinator)


class MergedSensor(_Base):
    entity_description: MergedSensorDescription

    def __init__(self, coordinator, entry, description: MergedSensorDescription) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        value = self.coordinator.data.current.get(self.entity_description.source_key)
        if value is None:
            return self.entity_description.default
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        source = self.coordinator.data.source.get(self.entity_description.source_key)
        return {"source": source} if source else {}


class LocalitySensor(_Base):
    _attr_icon = "mdi:city"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "locality")

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.location_name


class CurrentConditionSensor(_Base):
    _attr_icon = "mdi:weather-partly-cloudy"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "condition")

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.condition


class ImsLastUpdateSensor(_Base):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "ims_last_update")

    @property
    def native_value(self):
        return self.coordinator.data.ims_last_update


class WcLastUpdateSensor(_Base):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:clock-check"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "wc_last_update")

    @property
    def native_value(self):
        return self.coordinator.data.wc_last_update

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        return {
            "weathercloud_online": data.weathercloud_online,
            "station_url": data.station_url,
        }
