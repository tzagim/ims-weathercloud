from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_CITY,
    CONF_IMS_INTERVAL,
    CONF_LANGUAGE,
    CONF_WC_DEVICE_ID,
    CONF_WC_INTERVAL,
    CONF_WC_PASSWORD,
    CONF_WC_USERNAME,
    DEFAULT_IMS_INTERVAL,
    DEFAULT_LANGUAGE,
    DEFAULT_NAME,
    DEFAULT_WC_INTERVAL,
    DOMAIN,
    IMS_CITIES,
    MIN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

IMS_LOCATIONS_URL = "https://ims.gov.il/{lang}/locations_info"

_LANG_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=[
            SelectOptionDict(value="he", label="עברית"),
            SelectOptionDict(value="en", label="English"),
        ],
        mode=SelectSelectorMode.DROPDOWN,
    )
)


def _interval_selector() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=MIN_INTERVAL, max=1440, step=1, mode=NumberSelectorMode.BOX,
            unit_of_measurement="min",
        )
    )


def _norm_lang(language: str | None) -> str:
    return "he" if str(language).lower().startswith("he") else "en"


async def _fetch_localized_cities(hass: HomeAssistant, language: str) -> dict[str, str]:
    """Fetch {city_id: localized_name} from IMS in the chosen language.

    Falls back to the bundled English catalogue if the endpoint is unreachable.
    """
    lang = _norm_lang(language)
    session = async_get_clientsession(hass)
    try:
        async with session.get(IMS_LOCATIONS_URL.format(lang=lang)) as resp:
            if resp.status != 200:
                _LOGGER.warning("IMS locations_info returned %s", resp.status)
                return dict(IMS_CITIES)
            data = await resp.json(content_type=None)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Could not fetch IMS localized cities: %s", err)
        return dict(IMS_CITIES)

    cities = (data or {}).get("data") or {}
    result: dict[str, str] = {}
    for cid, city in cities.items():
        name = city.get("name") if isinstance(city, dict) else None
        result[str(cid)] = name or str(cid)
    return result or dict(IMS_CITIES)


def _city_selector(cities: dict[str, str]) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(value=cid, label=name)
                for cid, name in cities.items()
            ],
            mode=SelectSelectorMode.DROPDOWN,
            custom_value=False,
        )
    )


async def _validate_ims(hass: HomeAssistant, city: str, language: str) -> None:
    def _check() -> None:
        from weatheril import WeatherIL

        WeatherIL(str(city), language).get_current_analysis()

    await hass.async_add_executor_job(_check)


async def _validate_weathercloud(hass: HomeAssistant, device_id: str) -> None:
    def _check() -> None:
        from weathercloud import WeathercloudClient

        with WeathercloudClient() as client:
            client.get_current_conditions(device_id)

    await hass.async_add_executor_job(_check)


class ImsWeathercloudConfigFlow(ConfigFlow, domain=DOMAIN):
    """Two-step setup UI."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._cities: dict[str, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: language, Weathercloud, intervals."""
        if user_input is not None:
            self._data = {
                CONF_LANGUAGE: user_input[CONF_LANGUAGE],
                CONF_IMS_INTERVAL: int(user_input[CONF_IMS_INTERVAL]),
                CONF_WC_INTERVAL: int(user_input[CONF_WC_INTERVAL]),
            }
            wc_device = str(user_input.get(CONF_WC_DEVICE_ID, "")).strip()
            if wc_device:
                self._data[CONF_WC_DEVICE_ID] = wc_device
                if user_input.get(CONF_WC_USERNAME):
                    self._data[CONF_WC_USERNAME] = user_input[CONF_WC_USERNAME]
                if user_input.get(CONF_WC_PASSWORD):
                    self._data[CONF_WC_PASSWORD] = user_input[CONF_WC_PASSWORD]
            return await self.async_step_city()

        schema = vol.Schema(
            {
                vol.Required(CONF_LANGUAGE, default=DEFAULT_LANGUAGE): _LANG_SELECTOR,
                vol.Optional(CONF_WC_DEVICE_ID, default=""): str,
                vol.Optional(CONF_WC_USERNAME, default=""): str,
                vol.Optional(CONF_WC_PASSWORD, default=""): str,
                vol.Optional(CONF_IMS_INTERVAL, default=DEFAULT_IMS_INTERVAL): _interval_selector(),
                vol.Optional(CONF_WC_INTERVAL, default=DEFAULT_WC_INTERVAL): _interval_selector(),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_city(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: localized city dropdown."""
        errors: dict[str, str] = {}
        language = self._data[CONF_LANGUAGE]

        if not self._cities:
            self._cities = await _fetch_localized_cities(self.hass, language)

        if user_input is not None:
            city = str(user_input[CONF_CITY]).strip()
            wc_device = self._data.get(CONF_WC_DEVICE_ID, "")

            await self.async_set_unique_id(f"{city}_{wc_device or 'ims_only'}")
            self._abort_if_unique_id_configured()

            try:
                await _validate_ims(self.hass, city, language)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("IMS validation failed")
                errors["base"] = "ims_invalid"

            if not errors and wc_device:
                try:
                    await _validate_weathercloud(self.hass, wc_device)
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Weathercloud validation failed")
                    errors["base"] = "weathercloud_invalid"

            if not errors:
                data = dict(self._data)
                data[CONF_CITY] = city
                name = self._cities.get(city, city)
                return self.async_create_entry(
                    title=f"{DEFAULT_NAME} - {name}", data=data
                )

        default_city = next(iter(self._cities), "1")
        schema = vol.Schema(
            {vol.Required(CONF_CITY, default=default_city): _city_selector(self._cities)}
        )
        return self.async_show_form(step_id="city", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ImsWeathercloudOptionsFlow(config_entry)


class ImsWeathercloudOptionsFlow(OptionsFlow):
    """Change language and both refresh intervals after setup."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        data = self._config_entry.data
        options = self._config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_LANGUAGE,
                    default=options.get(CONF_LANGUAGE, data.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)),
                ): _LANG_SELECTOR,
                vol.Required(
                    CONF_IMS_INTERVAL,
                    default=options.get(CONF_IMS_INTERVAL, data.get(CONF_IMS_INTERVAL, DEFAULT_IMS_INTERVAL)),
                ): _interval_selector(),
                vol.Required(
                    CONF_WC_INTERVAL,
                    default=options.get(CONF_WC_INTERVAL, data.get(CONF_WC_INTERVAL, DEFAULT_WC_INTERVAL)),
                ): _interval_selector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
