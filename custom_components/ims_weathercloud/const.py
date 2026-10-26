from __future__ import annotations

from typing import Any

from homeassistant.components.weather import (
    ATTR_CONDITION_CLEAR_NIGHT,
    ATTR_CONDITION_CLOUDY,
    ATTR_CONDITION_EXCEPTIONAL,
    ATTR_CONDITION_FOG,
    ATTR_CONDITION_HAIL,
    ATTR_CONDITION_LIGHTNING_RAINY,
    ATTR_CONDITION_PARTLYCLOUDY,
    ATTR_CONDITION_POURING,
    ATTR_CONDITION_RAINY,
    ATTR_CONDITION_SNOWY,
    ATTR_CONDITION_SNOWY_RAINY,
    ATTR_CONDITION_SUNNY,
    ATTR_CONDITION_WINDY,
)

DOMAIN = "ims_weathercloud"
PLATFORMS = ["weather", "sensor", "button"]

DEFAULT_NAME = "IMS + Weathercloud"

# --- Config keys ---------------------------------------------------------
CONF_CITY = "city"
CONF_LANGUAGE = "language"
CONF_WC_DEVICE_ID = "wc_device_id"
CONF_WC_USERNAME = "wc_username"
CONF_WC_PASSWORD = "wc_password"
CONF_IMS_INTERVAL = "ims_interval"
CONF_WC_INTERVAL = "wc_interval"

DEFAULT_LANGUAGE = "he"
DEFAULT_IMS_INTERVAL = 60
DEFAULT_WC_INTERVAL = 10
MIN_INTERVAL = 1

SOURCE_IMS = "ims"
SOURCE_WEATHERCLOUD = "weathercloud"

# weatheril reports wind in km/h, weathercloud in m/s -> normalise before merge.
MS_TO_KMH = 3.6

WEATHERCLOUD_STATION_URL = "https://app.weathercloud.net/d{device_id}"


def ims_site_url(language: str | None) -> str:
    """IMS site in the language the user picked (fallback link when no station)."""
    lang = "en" if str(language).lower().startswith("en") else "he"
    return f"https://ims.gov.il/{lang}"


# --- Wind direction: IMS reports an index (1-17), not degrees ------------
# Source: https://ims.gov.il/en/wind_directions  (mirrors the IMS component)
WIND_DIRECTIONS: dict[int | None, float | None] = {
    None: None, 0: None,
    1: 360.0, 2: 23.0, 3: 45.0, 4: 68.0, 5: 90.0, 6: 113.0, 7: 135.0, 8: 150.0,
    9: 180.0, 10: 203.0, 11: 225.0, 12: 248.0, 13: 270.0, 14: 293.0, 15: 315.0,
    16: 338.0, 17: 0.0,
}


def ims_wind_bearing(direction_id: object) -> float | None:
    """Map an IMS wind_direction_id index to degrees."""
    try:
        return WIND_DIRECTIONS.get(int(direction_id))
    except (TypeError, ValueError):
        return None


# --- IMS weather_code -> HA condition (mirrors the IMS component) ---------
WEATHER_CODE_TO_CONDITION: dict[str, str | None] = {
    "1010": ATTR_CONDITION_EXCEPTIONAL,
    "1020": ATTR_CONDITION_LIGHTNING_RAINY,
    "1060": ATTR_CONDITION_SNOWY,
    "1070": ATTR_CONDITION_SNOWY,
    "1080": ATTR_CONDITION_SNOWY_RAINY,
    "1140": ATTR_CONDITION_POURING,
    "1160": ATTR_CONDITION_FOG,
    "1220": ATTR_CONDITION_PARTLYCLOUDY,
    "1220-night": ATTR_CONDITION_PARTLYCLOUDY,
    "1230": ATTR_CONDITION_CLOUDY,
    "1250": ATTR_CONDITION_SUNNY,
    "1250-night": ATTR_CONDITION_CLEAR_NIGHT,
    "1260": ATTR_CONDITION_WINDY,
    "1270": ATTR_CONDITION_SUNNY,
    "1300": ATTR_CONDITION_HAIL,
    "1310": ATTR_CONDITION_SUNNY,
    "1320": ATTR_CONDITION_HAIL,
    "1510": ATTR_CONDITION_LIGHTNING_RAINY,
    "1520": ATTR_CONDITION_SNOWY,
    "1530": ATTR_CONDITION_RAINY,
    "1540": ATTR_CONDITION_RAINY,
    "1560": ATTR_CONDITION_RAINY,
    "1570": ATTR_CONDITION_EXCEPTIONAL,
    "1580": ATTR_CONDITION_EXCEPTIONAL,
    "1590": ATTR_CONDITION_EXCEPTIONAL,
}

_NIGHT_CODES = {"1220", "1250"}


def ims_condition(code: str | None, hour: int | None = None) -> str | None:
    """Translate an IMS weather_code to a HA condition string.

    At night (hour < 6 or > 20) the 1220/1250 codes map to their -night
    variant, matching the IMS component behaviour.
    """
    if code is None:
        return None
    key = str(code)
    if hour is not None and key in _NIGHT_CODES and (hour < 6 or hour > 20):
        key = f"{key}-night"
    return WEATHER_CODE_TO_CONDITION.get(key)


def locality_name(entry: Any, data: Any) -> str:
    """Device name: the locality IMS reports, else the one picked at setup.

    The entry title is "<DEFAULT_NAME> - <locality as IMS listed it>", so it
    already holds the localized name without a bundled city list.
    """
    name = getattr(data, "location_name", None)
    if name:
        return name
    title = str(getattr(entry, "title", "") or "")
    return title.removeprefix(f"{DEFAULT_NAME} - ").strip() or DEFAULT_NAME


# --- custom weather icons (theme) ---------------------------------------
CONF_CUSTOM_ICONS = "custom_icons"
CONF_ICONS_TARGET = "icons_target"  # theme to inject into, or "__new__"
# Put the Weathercloud station's position on the weather entity (map card).
CONF_STATION_LOCATION = "station_location"
DEFAULT_STATION_LOCATION = True
THEME_NAME = "weather_animation_icons"
THEME_FILE = "weather_animation_icons.yaml"
ICONS_DIRNAME = "weather_icons"
ICONS_URL = "/ims_weathercloud/weather_icons"
PROFILE_URL = "https://my.home-assistant.io/redirect/profile"

WEATHER_ICON_MAP = {
    "clear-night": "clear-night.svg",
    "cloudy": "cloudy.svg",
    "exceptional": "exceptional.svg",
    "fog": "fog.svg",
    "hail": "hail.svg",
    "lightning": "lightning.svg",
    "lightning-rainy": "lightning.svg",
    "partlycloudy": "partlycloudy.svg",
    "pouring": "pouring.svg",
    "rainy": "rainy.svg",
    "snowy": "snowy.svg",
    "snowy-rainy": "snowy-rainy.svg",
    "sunny": "sunny.svg",
    "windy": "windy.svg",
    "windy-variant": "windy-variant.svg",
}
