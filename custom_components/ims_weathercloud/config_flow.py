from __future__ import annotations

import logging
from collections.abc import Mapping
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
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .theme_installer import NEW_THEME_SENTINEL, async_discover_themes
from .const import (
    CONF_CUSTOM_ICONS,
    CONF_ICONS_TARGET,
    THEME_NAME,
    CONF_CITY,
    CONF_IMS_INTERVAL,
    CONF_LANGUAGE,
    CONF_STATION_LOCATION,
    CONF_WC_DEVICE_ID,
    CONF_WC_INTERVAL,
    CONF_WC_PASSWORD,
    CONF_WC_USERNAME,
    DEFAULT_IMS_INTERVAL,
    DEFAULT_LANGUAGE,
    DEFAULT_NAME,
    DEFAULT_STATION_LOCATION,
    DEFAULT_WC_INTERVAL,
    DOMAIN,
    MIN_INTERVAL,
)
from .coordinator import create_weathercloud_http
from .weathercloud_api import WeathercloudApi, WeathercloudAuthError

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

    IMS is the only source of the list. Returns an empty dict when it can't
    be loaded; the flow then asks the user to try again.
    """
    lang = _norm_lang(language)
    session = async_get_clientsession(hass)
    try:
        async with session.get(IMS_LOCATIONS_URL.format(lang=lang)) as resp:
            if resp.status != 200:
                _LOGGER.warning("IMS locations_info returned %s", resp.status)
                return {}
            data = await resp.json(content_type=None)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Could not fetch IMS localized cities: %s", err)
        return {}

    cities = (data or {}).get("data") if isinstance(data, dict) else None
    if not isinstance(cities, dict):
        _LOGGER.warning("IMS locations_info had no locality list")
        return {}
    result: dict[str, str] = {}
    for cid, city in cities.items():
        name = city.get("name") if isinstance(city, dict) else None
        result[str(cid)] = name or str(cid)
    return result


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


async def _validate_weathercloud(
    hass: HomeAssistant,
    device_id: str,
    username: str | None = None,
    password: str | None = None,
) -> None:
    """Fetch the station once; check the login too when credentials are given.

    Raises WeathercloudAuthError for rejected credentials, anything else means
    the station could not be read.
    """
    api = WeathercloudApi(create_weathercloud_http(), device_id)
    try:
        await api.async_get_values()
    finally:
        await api.async_close()

    if username and password:
        api = WeathercloudApi(
            create_weathercloud_http(), device_id, username, password
        )
        try:
            await api.async_login()
        finally:
            await api.async_close()


_PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


async def _weathercloud_errors(
    hass: HomeAssistant,
    device_id: str,
    username: str | None,
    password: str | None,
) -> dict[str, str]:
    """Validate a station (and login); return form errors, empty if fine."""
    try:
        await _validate_weathercloud(hass, device_id, username, password)
    except WeathercloudAuthError:
        return {"base": "weathercloud_auth"}
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Weathercloud validation failed")
        return {"base": "weathercloud_invalid"}
    return {}


class ImsWeathercloudConfigFlow(ConfigFlow, domain=DOMAIN):
    """Two-step setup UI."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._cities: dict[str, str] = {}
        self._cities_language: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: language, Weathercloud, intervals."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._data = {
                CONF_LANGUAGE: user_input[CONF_LANGUAGE],
                CONF_IMS_INTERVAL: int(user_input[CONF_IMS_INTERVAL]),
                CONF_WC_INTERVAL: int(user_input[CONF_WC_INTERVAL]),
                CONF_CUSTOM_ICONS: bool(user_input.get(CONF_CUSTOM_ICONS, False)),
            }
            wc_device = str(user_input.get(CONF_WC_DEVICE_ID, "")).strip()
            if wc_device:
                self._data[CONF_WC_DEVICE_ID] = wc_device
                if user_input.get(CONF_WC_USERNAME):
                    self._data[CONF_WC_USERNAME] = user_input[CONF_WC_USERNAME]
                if user_input.get(CONF_WC_PASSWORD):
                    self._data[CONF_WC_PASSWORD] = user_input[CONF_WC_PASSWORD]

                # Checked here, on the form that has these fields, so a typo
                # can be fixed without starting over.
                errors = await _weathercloud_errors(
                    self.hass,
                    wc_device,
                    self._data.get(CONF_WC_USERNAME),
                    self._data.get(CONF_WC_PASSWORD),
                )

            if not errors:
                # The locality list comes only from IMS, in the chosen language.
                if self._cities_language != self._data[CONF_LANGUAGE]:
                    self._cities = await _fetch_localized_cities(
                        self.hass, self._data[CONF_LANGUAGE]
                    )
                    self._cities_language = (
                        self._data[CONF_LANGUAGE] if self._cities else None
                    )
                if not self._cities:
                    errors["base"] = "ims_cities_unavailable"

            if not errors:
                return await self.async_step_city()

        schema = vol.Schema(
            {
                vol.Required(CONF_LANGUAGE, default=DEFAULT_LANGUAGE): _LANG_SELECTOR,
                vol.Optional(CONF_WC_DEVICE_ID, default=""): str,
                vol.Optional(CONF_WC_USERNAME, default=""): str,
                vol.Optional(CONF_WC_PASSWORD, default=""): _PASSWORD_SELECTOR,
                vol.Optional(CONF_IMS_INTERVAL, default=DEFAULT_IMS_INTERVAL): _interval_selector(),
                vol.Optional(CONF_WC_INTERVAL, default=DEFAULT_WC_INTERVAL): _interval_selector(),
                vol.Optional(CONF_CUSTOM_ICONS, default=False): bool,
            }
        )
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_city(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: localized city dropdown."""
        errors: dict[str, str] = {}
        language = self._data[CONF_LANGUAGE]

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

            if not errors:
                data = dict(self._data)
                data[CONF_CITY] = city
                name = self._cities.get(city, city)
                return self.async_create_entry(
                    title=f"{DEFAULT_NAME} - {name}", data=data
                )

        default_city = next(iter(self._cities))
        schema = vol.Schema(
            {vol.Required(CONF_CITY, default=default_city): _city_selector(self._cities)}
        )
        return self.async_show_form(step_id="city", data_schema=schema, errors=errors)

    # --- change station / login after setup -----------------------------
    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the Weathercloud station and login of an existing entry."""
        entry = self._get_reconfigure_entry()
        current = entry.data
        errors: dict[str, str] = {}

        if user_input is not None:
            device = str(user_input.get(CONF_WC_DEVICE_ID, "")).strip()
            username = str(user_input.get(CONF_WC_USERNAME, "")).strip()
            password = user_input.get(CONF_WC_PASSWORD) or ""
            # An empty password keeps the saved one for the same username.
            if (
                username
                and not password
                and username == current.get(CONF_WC_USERNAME)
            ):
                password = current.get(CONF_WC_PASSWORD, "")

            new_data = {
                k: v
                for k, v in current.items()
                if k not in (CONF_WC_DEVICE_ID, CONF_WC_USERNAME, CONF_WC_PASSWORD)
            }
            if device:
                new_data[CONF_WC_DEVICE_ID] = device
                if username and password:
                    new_data[CONF_WC_USERNAME] = username
                    new_data[CONF_WC_PASSWORD] = password

            new_uid = f"{current[CONF_CITY]}_{device or 'ims_only'}"
            if new_uid != entry.unique_id and any(
                e.unique_id == new_uid
                for e in self._async_current_entries(include_ignore=False)
            ):
                errors["base"] = "already_configured"

            if not errors and device:
                errors.update(
                    await _weathercloud_errors(
                        self.hass,
                        device,
                        new_data.get(CONF_WC_USERNAME),
                        new_data.get(CONF_WC_PASSWORD),
                    )
                )

            if not errors:
                return self.async_update_reload_and_abort(
                    entry, unique_id=new_uid, data=new_data
                )

        schema = self.add_suggested_values_to_schema(
            vol.Schema(
                {
                    vol.Optional(CONF_WC_DEVICE_ID): str,
                    vol.Optional(CONF_WC_USERNAME): str,
                    vol.Optional(CONF_WC_PASSWORD): _PASSWORD_SELECTOR,
                }
            ),
            {
                CONF_WC_DEVICE_ID: (user_input or current).get(CONF_WC_DEVICE_ID, ""),
                CONF_WC_USERNAME: (user_input or current).get(CONF_WC_USERNAME, ""),
            },
        )
        return self.async_show_form(
            step_id="reconfigure", data_schema=schema, errors=errors
        )

    # --- Weathercloud rejected the saved password ------------------------
    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new Weathercloud password (or drop the login)."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            username = str(user_input.get(CONF_WC_USERNAME, "")).strip()
            password = user_input.get(CONF_WC_PASSWORD) or ""
            new_data = {
                k: v
                for k, v in entry.data.items()
                if k not in (CONF_WC_USERNAME, CONF_WC_PASSWORD)
            }
            if username or password:
                if not (username and password):
                    errors["base"] = "weathercloud_auth"
                else:
                    new_data[CONF_WC_USERNAME] = username
                    new_data[CONF_WC_PASSWORD] = password
                    errors.update(
                        await _weathercloud_errors(
                            self.hass, entry.data[CONF_WC_DEVICE_ID], username, password
                        )
                    )
            if not errors:
                return self.async_update_reload_and_abort(entry, data=new_data)

        schema = self.add_suggested_values_to_schema(
            vol.Schema(
                {
                    vol.Optional(CONF_WC_USERNAME): str,
                    vol.Optional(CONF_WC_PASSWORD): _PASSWORD_SELECTOR,
                }
            ),
            {CONF_WC_USERNAME: (user_input or entry.data).get(CONF_WC_USERNAME, "")},
        )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
            description_placeholders={"station": entry.data.get(CONF_WC_DEVICE_ID, "")},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ImsWeathercloudOptionsFlow(config_entry)


class ImsWeathercloudOptionsFlow(OptionsFlow):
    """Options: settings + optional custom-icons theme picker (second screen)."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry
        self._pending: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        data = self._config_entry.data
        options = self._config_entry.options

        if user_input is not None:
            self._pending = dict(user_input)
            was_on = options.get(CONF_CUSTOM_ICONS, data.get(CONF_CUSTOM_ICONS, False))
            now_on = user_input.get(CONF_CUSTOM_ICONS)
            prev_target = options.get(CONF_ICONS_TARGET, data.get(CONF_ICONS_TARGET))

            if now_on and (not was_on or not prev_target):
                return await self.async_step_icons()

            # otherwise keep the existing target (if any) and finish now
            self._pending[CONF_ICONS_TARGET] = prev_target or NEW_THEME_SENTINEL
            return self.async_create_entry(title="", data=self._pending)

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
                vol.Required(
                    CONF_CUSTOM_ICONS,
                    default=options.get(CONF_CUSTOM_ICONS, data.get(CONF_CUSTOM_ICONS, False)),
                ): bool,
            }
        )
        if data.get(CONF_WC_DEVICE_ID):
            schema = schema.extend(
                {
                    vol.Required(
                        CONF_STATION_LOCATION,
                        default=options.get(
                            CONF_STATION_LOCATION,
                            data.get(CONF_STATION_LOCATION, DEFAULT_STATION_LOCATION),
                        ),
                    ): bool,
                }
            )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_icons(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._pending[CONF_ICONS_TARGET] = user_input[CONF_ICONS_TARGET]
            return self.async_create_entry(title="", data=self._pending)

        themes = await async_discover_themes(self.hass)
        options = [
            SelectOptionDict(value=NEW_THEME_SENTINEL, label=f"➕ New theme ({THEME_NAME})")
        ] + [SelectOptionDict(value=name, label=name) for name in themes]

        prev = self._config_entry.options.get(
            CONF_ICONS_TARGET,
            self._config_entry.data.get(CONF_ICONS_TARGET, NEW_THEME_SENTINEL),
        )
        if prev not in themes and prev != NEW_THEME_SENTINEL:
            prev = NEW_THEME_SENTINEL

        schema = vol.Schema(
            {
                vol.Required(CONF_ICONS_TARGET, default=prev): SelectSelector(
                    SelectSelectorConfig(
                        options=options, mode=SelectSelectorMode.DROPDOWN
                    )
                )
            }
        )
        return self.async_show_form(step_id="icons", data_schema=schema)
