from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CITY,
    CONF_IMS_INTERVAL,
    CONF_LANGUAGE,
    CONF_WC_DEVICE_ID,
    CONF_WC_INTERVAL,
    CONF_WC_PASSWORD,
    CONF_WC_USERNAME,
    DEFAULT_IMS_INTERVAL,
    DEFAULT_WC_INTERVAL,
    MIN_INTERVAL,
    MS_TO_KMH,
    SOURCE_IMS,
    SOURCE_WEATHERCLOUD,
    ims_condition,
    ims_wind_bearing,
)

_LOGGER = logging.getLogger(__name__)

# Grace so a scheduler tick that fires a hair early still counts as "due"
# (prevents a 10-min source from effectively refreshing every 20 min).
_DUE_GRACE = timedelta(seconds=30)


def _safe(obj: Any, *names: str) -> Any:
    for name in names:
        value = getattr(obj, name, None)
        if value not in (None, ""):
            return value
    return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    f = _to_float(value)
    return int(f) if f is not None else None


def _rain_chance_pct(value: Any) -> int | None:
    """IMS rain_chance is a 0-1 fraction; expose as a 0-100 percentage."""
    f = _to_float(value)
    if f is None:
        return None
    return int(round(f * 100)) if f <= 1 else int(round(f))


@dataclass
class MergedData:
    current: dict[str, Any] = field(default_factory=dict)
    source: dict[str, str] = field(default_factory=dict)
    condition: str | None = None
    forecast_daily: list[dict[str, Any]] = field(default_factory=list)
    forecast_hourly: list[dict[str, Any]] = field(default_factory=list)
    weathercloud_online: bool = False
    location_name: str | None = None
    ims_last_update: datetime | None = None   # station/observation time
    wc_last_update: datetime | None = None     # station reading time (epoch)
    ims_fetched_at: datetime | None = None     # when HA last polled IMS
    wc_fetched_at: datetime | None = None      # when HA last polled Weathercloud
    station_url: str | None = None


class ImsWeathercloudCoordinator(DataUpdateCoordinator[MergedData]):
    """Fetch IMS + Weathercloud and expose a single merged snapshot."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self._city = entry.data[CONF_CITY]
        self.language: str = entry.data.get(CONF_LANGUAGE, "he")
        self._wc_device_id: str | None = entry.data.get(CONF_WC_DEVICE_ID) or None
        self._wc_username: str | None = entry.data.get(CONF_WC_USERNAME) or None
        self._wc_password: str | None = entry.data.get(CONF_WC_PASSWORD) or None

        self._ims_interval = int(
            entry.options.get(
                CONF_IMS_INTERVAL, entry.data.get(CONF_IMS_INTERVAL, DEFAULT_IMS_INTERVAL)
            )
        )
        self._wc_interval = int(
            entry.options.get(
                CONF_WC_INTERVAL, entry.data.get(CONF_WC_INTERVAL, DEFAULT_WC_INTERVAL)
            )
        )
        base = max(MIN_INTERVAL, min(self._ims_interval, self._wc_interval))
        super().__init__(
            hass, _LOGGER, name="ims_weathercloud",
            update_interval=timedelta(minutes=base),
        )

        self._ims_cache: tuple[Any, Any] | None = None
        self._wc_cache: Any | None = None
        self._last_ims_fetch: datetime | None = None
        self._last_wc_fetch: datetime | None = None
        self._force_all = False  # set by the manual Refresh button
        self._ims_ok = True      # for throttled failure logging
        self._wc_ok = True

    async def async_force_refresh(self) -> None:
        """Force both sources to refetch now (bypasses the per-source cache)."""
        self._force_all = True
        await self.async_request_refresh()

    # --- blocking fetchers ----------------------------------------------
    def _fetch_ims(self) -> tuple[Any, Any]:
        from weatheril import WeatherIL

        weather = WeatherIL(str(self._city), self.language)
        return weather.get_current_analysis(), weather.get_forecast()

    def _fetch_weathercloud(self) -> Any | None:
        if not self._wc_device_id:
            return None
        from weathercloud import WeathercloudClient, WeathercloudError

        kwargs: dict[str, Any] = {}
        if self._wc_username and self._wc_password:
            kwargs["username"] = self._wc_username
            kwargs["password"] = self._wc_password
        try:
            with WeathercloudClient(**kwargs) as client:
                return client.get_current_conditions(self._wc_device_id)
        except WeathercloudError as err:
            _LOGGER.warning("Weathercloud fetch failed, falling back to IMS: %s", err)
            return None

    # --- normalise IMS current ------------------------------------------
    def _build_ims_current(self, w: Any) -> dict[str, Any]:
        return {
            "temperature": _to_float(_safe(w, "temperature")),
            "apparent_temperature": _to_float(_safe(w, "feels_like")),
            "humidity": _to_int(_safe(w, "humidity", "relative_humidity")),
            "wind_speed": _to_float(_safe(w, "wind_speed")),                 # km/h
            "wind_gust": _to_float(_safe(w, "gust_speed")),                  # km/h
            "wind_bearing": ims_wind_bearing(_safe(w, "wind_direction_id")),  # deg
            "rain": _to_float(_safe(w, "rain")),
            "precipitation_probability": _rain_chance_pct(_safe(w, "rain_chance")),
            "uv_index": _to_int(_safe(w, "u_v_index", "uv_index")),
            "dew_point": _to_float(_safe(w, "due_point_temp", "dew_point")),
            "pm10": _to_float(_safe(w, "pm10")),
            # pressure/solar are not provided by IMS -> Weathercloud only
        }

    # --- apply Weathercloud overrides -----------------------------------
    def _apply_weathercloud(
        self, current: dict[str, Any], source: dict[str, str], wc: Any
    ) -> datetime | None:
        wind_ms = _to_float(getattr(wc, "wind_speed", None))
        wind_avg_ms = _to_float(getattr(wc, "wind_speed_avg", None))
        gust_ms = _to_float(getattr(wc, "wind_gust", None))

        overrides: dict[str, Any] = {
            "temperature": _to_float(getattr(wc, "temperature", None)),
            "apparent_temperature": _to_float(getattr(wc, "heat_index", None)),
            "humidity": _to_int(getattr(wc, "humidity", None)),
            "wind_speed": None if wind_ms is None else round(wind_ms * MS_TO_KMH, 1),
            "wind_speed_avg": None if wind_avg_ms is None else round(wind_avg_ms * MS_TO_KMH, 1),
            "wind_gust": None if gust_ms is None else round(gust_ms * MS_TO_KMH, 1),
            "wind_bearing": _to_int(getattr(wc, "wind_direction", None)),
            "wind_bearing_avg": _to_int(getattr(wc, "wind_direction_avg", None)),
            "pressure": _to_float(getattr(wc, "pressure", None)),
            "rain": _to_float(getattr(wc, "rain", None)),
            "rain_rate": _to_float(getattr(wc, "rain_rate", None)),
            "uv_index": _to_int(getattr(wc, "uv_index", None)),
            "dew_point": _to_float(getattr(wc, "dew_point", None)),
            "solar_radiation": _to_float(getattr(wc, "solar_radiation", None)),
            "inside_temperature": _to_float(getattr(wc, "inside_temperature", None)),
            "inside_humidity": _to_int(getattr(wc, "inside_humidity", None)),
        }
        for key, value in overrides.items():
            if value is not None:
                current[key] = value
                source[key] = SOURCE_WEATHERCLOUD

        epoch = _to_int(getattr(wc, "epoch", None))
        return datetime.fromtimestamp(epoch, tz=timezone.utc) if epoch else None

    # --- forecast --------------------------------------------------------
    def _build_forecast(self, forecast: Any) -> tuple[list[dict], list[dict]]:
        daily: list[dict[str, Any]] = []
        hourly: list[dict[str, Any]] = []
        for day in getattr(forecast, "days", None) or []:
            daily.append(
                {
                    "datetime": _safe(day, "date"),
                    "condition": ims_condition(_safe(day, "weather_code")),
                    "native_temperature": _to_float(_safe(day, "maximum_temperature")),
                    "native_templow": _to_float(_safe(day, "minimum_temperature")),
                    "uv_index": _to_int(_safe(day, "maximum_uvi")),
                    "native_precipitation": _to_float(_safe(day, "rain")),
                }
            )
            for hour in getattr(day, "hours", None) or []:
                hh = _safe(hour, "hour")  # "HH:MM"
                hour_int = None
                if isinstance(hh, str) and ":" in hh:
                    hour_int = _to_int(hh.split(":")[0])
                hourly.append(
                    {
                        "datetime": _safe(hour, "forecast_time"),
                        "condition": ims_condition(_safe(hour, "weather_code"), hour_int),
                        "native_temperature": _to_float(
                            _safe(hour, "precise_temperature", "temperature")
                        ),
                        "native_wind_speed": _to_float(_safe(hour, "wind_speed")),
                        "native_wind_gust_speed": _to_float(_safe(hour, "gust_speed")),
                        "wind_bearing": ims_wind_bearing(_safe(hour, "wind_direction_id")),
                        "humidity": _to_int(_safe(hour, "relative_humidity")),
                        "native_precipitation": _to_float(_safe(hour, "rain")),
                        "precipitation_probability": _rain_chance_pct(
                            _safe(hour, "rain_chance")
                        ),
                        "uv_index": _to_int(_safe(hour, "u_v_index")),
                    }
                )
        return daily, hourly

    # --- coordinator entry point ----------------------------------------
    async def _async_update_data(self) -> MergedData:
        now = dt_util.utcnow()

        force = self._force_all
        self._force_all = False

        ims_due = (
            force
            or self._ims_cache is None
            or self._last_ims_fetch is None
            or (now - self._last_ims_fetch) >= timedelta(minutes=self._ims_interval) - _DUE_GRACE
        )
        if ims_due:
            try:
                self._ims_cache = await self.hass.async_add_executor_job(self._fetch_ims)
                self._last_ims_fetch = now
                if not self._ims_ok:
                    _LOGGER.info("IMS connection restored")
                    self._ims_ok = True
            except Exception as err:  # noqa: BLE001
                if self._ims_cache is None:
                    raise UpdateFailed(f"IMS fetch failed: {err}") from err
                # Warn once, then stay quiet and keep serving the last good data until IMS recovers.
                if self._ims_ok:
                    _LOGGER.warning(
                        "IMS temporarily unavailable, using cached data: %s", err
                    )
                    self._ims_ok = False
        ims_current, ims_forecast = self._ims_cache

        wc = None
        if self._wc_device_id:
            wc_due = (
                force
                or self._last_wc_fetch is None
                or (now - self._last_wc_fetch) >= timedelta(minutes=self._wc_interval) - _DUE_GRACE
            )
            if wc_due:
                try:
                    self._wc_cache = await self.hass.async_add_executor_job(
                        self._fetch_weathercloud
                    )
                    self._last_wc_fetch = now
                    if not self._wc_ok:
                        _LOGGER.info("Weathercloud connection restored")
                        self._wc_ok = True
                except Exception as err:  # noqa: BLE001
                    if self._wc_ok:
                        _LOGGER.warning(
                            "Weathercloud temporarily unavailable, using cached data: %s",
                            err,
                        )
                        self._wc_ok = False
            wc = self._wc_cache

        current = self._build_ims_current(ims_current)
        source = {key: SOURCE_IMS for key in current}

        wc_online = False
        wc_last_update: datetime | None = None
        if wc is not None:
            wc_last_update = self._apply_weathercloud(current, source, wc)
            wc_online = True

        # IMS observation time (condition is night-aware off it)
        ims_time = _safe(ims_current, "forecast_time")
        ims_last_update = ims_time if isinstance(ims_time, datetime) else self._last_ims_fetch
        hour_int = ims_time.hour if isinstance(ims_time, datetime) else None
        condition = ims_condition(_safe(ims_current, "weather_code"), hour_int)

        daily, hourly = self._build_forecast(ims_forecast)

        station_url = (
            f"https://app.weathercloud.net/d{self._wc_device_id}"
            if self._wc_device_id else None
        )

        return MergedData(
            current=current,
            source=source,
            condition=condition,
            forecast_daily=daily,
            forecast_hourly=hourly,
            weathercloud_online=wc_online,
            location_name=_safe(ims_current, "location"),
            ims_last_update=ims_last_update,
            wc_last_update=wc_last_update,
            ims_fetched_at=self._last_ims_fetch,
            wc_fetched_at=self._last_wc_fetch,
            station_url=station_url,
        )
