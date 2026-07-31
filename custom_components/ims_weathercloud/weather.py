"""Weather entity for the merged IMS + Weathercloud integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPressure, UnitOfSpeed, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN, IMS_CITIES, ims_site_url
from .coordinator import ImsWeathercloudCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: ImsWeathercloudCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ImsWeathercloudWeather(coordinator, entry)])


class ImsWeathercloudWeather(CoordinatorEntity[ImsWeathercloudCoordinator], WeatherEntity):
    """Weather entity whose current values may come from Weathercloud."""

    _attr_has_entity_name = True
    _attr_name = None  # use the device (locality) name
    _attr_attribution = "Data provided by IMS / Weathercloud"
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY
    )

    def __init__(self, coordinator: ImsWeathercloudCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_weather"
        # (#5) device name = IMS locality
        name = (
            getattr(coordinator.data, "location_name", None)
            or IMS_CITIES.get(str(entry.data.get("city")), DEFAULT_NAME)
        )
        url = getattr(coordinator.data, "station_url", None) or ims_site_url(
            entry.data.get("language")
        )
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": name,
            "manufacturer": "IMS + Weathercloud",
            "entry_type": "service",
            "configuration_url": url,
        }

    def _c(self, key: str) -> Any:
        return self.coordinator.data.current.get(key)

    @property
    def condition(self) -> str | None:
        return self.coordinator.data.condition

    @property
    def native_temperature(self) -> float | None:
        return self._c("temperature")

    @property
    def native_apparent_temperature(self) -> float | None:
        return self._c("apparent_temperature")

    @property
    def humidity(self) -> float | None:
        return self._c("humidity")

    @property
    def native_wind_speed(self) -> float | None:
        return self._c("wind_speed")

    @property
    def native_wind_gust_speed(self) -> float | None:
        return self._c("wind_gust")

    @property
    def wind_bearing(self) -> float | None:
        return self._c("wind_bearing")

    @property
    def native_pressure(self) -> float | None:
        return self._c("pressure")

    @property
    def native_dew_point(self) -> float | None:
        return self._c("dew_point")

    @property
    def uv_index(self) -> float | None:
        return self._c("uv_index")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        return {
            "current_source": data.source,
            "weathercloud_online": data.weathercloud_online,
            "locality": data.location_name,
            "station_url": data.station_url,
        }

    async def async_forecast_daily(self) -> list[Forecast] | None:
        return [Forecast(**d) for d in self.coordinator.data.forecast_daily]  # type: ignore[misc]

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        return [Forecast(**h) for h in self.coordinator.data.forecast_hourly]  # type: ignore[misc]

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
