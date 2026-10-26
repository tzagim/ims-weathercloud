"""End-to-end tests inside a real Home Assistant (no network).

IMS is replaced by a fixed snapshot; Weathercloud is the fake server from
test_weathercloud_api.py behind an httpx MockTransport.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

try:  # helper only shipped by newer pytest-homeassistant-custom-component
    from pytest_homeassistant_custom_component.components.diagnostics import (
        get_diagnostics_for_config_entry,
    )
except ImportError:  # pragma: no cover
    get_diagnostics_for_config_entry = None

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_weathercloud_api import FakeWeathercloud  # noqa: E402

from custom_components.ims_weathercloud.const import (  # noqa: E402
    CONF_CITY,
    CONF_LANGUAGE,
    CONF_STATION_LOCATION,
    CONF_WC_DEVICE_ID,
    CONF_WC_PASSWORD,
    CONF_WC_USERNAME,
    DOMAIN,
    SOURCE_IMS,
    SOURCE_WEATHERCLOUD,
)

PKG = "custom_components.ims_weathercloud"
DEVICE = "3930075612"

IMS_CURRENT = SimpleNamespace(
    temperature=18.0, feels_like=17.0, humidity=70, wind_speed=10.0,
    gust_speed=15.0, wind_direction_id=13, rain=0.0, rain_chance=0.1,
    u_v_index=2, due_point_temp=12.0, pm10=20.0, weather_code="1250",
    forecast_time=None, location="Tel Aviv",
)
IMS_FORECAST = SimpleNamespace(days=[])


@pytest.fixture
def server():
    return FakeWeathercloud()


@pytest.fixture
def created_clients():
    return []


@pytest.fixture(autouse=True)
def fakes(server, created_clients):
    def _http():
        client = httpx.AsyncClient(transport=httpx.MockTransport(server.handler))
        created_clients.append(client)
        return client

    with (
        patch(f"{PKG}.coordinator.create_weathercloud_http", _http),
        patch(f"{PKG}.config_flow.create_weathercloud_http", _http),
        patch(
            f"{PKG}.coordinator.ImsWeathercloudCoordinator._fetch_ims",
            return_value=(IMS_CURRENT, IMS_FORECAST),
        ),
        patch(f"{PKG}.config_flow._validate_ims", return_value=None),
        patch(f"{PKG}.config_flow._fetch_localized_cities", return_value={"2": "Tel Aviv"}),
        patch(f"{PKG}.async_register_icon_path", return_value=None),
        patch(f"{PKG}._async_apply_icons_state", return_value=None),
    ):
        yield


def _entry(**extra) -> MockConfigEntry:
    data = {CONF_CITY: "2", CONF_LANGUAGE: "en", **extra}
    return MockConfigEntry(domain=DOMAIN, data=data, unique_id="2_test")


async def _setup(hass: HomeAssistant, entry: MockConfigEntry):
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return hass.data[DOMAIN][entry.entry_id]


async def test_station_overrides_ims(hass: HomeAssistant, created_clients) -> None:
    coordinator = await _setup(hass, _entry(**{CONF_WC_DEVICE_ID: DEVICE}))
    data = coordinator.data
    assert data.weathercloud_online
    assert data.current["temperature"] == 21.4
    assert data.source["temperature"] == SOURCE_WEATHERCLOUD
    assert data.current["wind_speed"] == round(3.1 * 3.6, 1)  # m/s -> km/h
    assert data.current["pressure"] == 1013.2
    assert data.current["uv_index"] == 3
    assert data.current["pm10"] == 20.0 and data.source["pm10"] == SOURCE_IMS
    assert "inside_temperature" not in data.current
    assert data.wc_last_update is not None


async def test_indoor_sensors_with_login(hass: HomeAssistant, server) -> None:
    coordinator = await _setup(
        hass,
        _entry(**{CONF_WC_DEVICE_ID: DEVICE, CONF_WC_USERNAME: "me", CONF_WC_PASSWORD: "secret"}),
    )
    assert coordinator.data.current["inside_temperature"] == 24.0
    assert coordinator.data.current["inside_humidity"] == 48

    await coordinator.async_force_refresh()
    await hass.async_block_till_done()
    assert server.logins == 1  # session is kept between polls


async def test_station_down_falls_back_to_ims(hass: HomeAssistant, server) -> None:
    server.fail_values_with = 500
    coordinator = await _setup(hass, _entry(**{CONF_WC_DEVICE_ID: DEVICE}))
    assert not coordinator.data.weathercloud_online
    assert coordinator.data.current["temperature"] == 18.0
    assert coordinator.data.source["temperature"] == SOURCE_IMS


async def test_unload_closes_session(hass: HomeAssistant, created_clients) -> None:
    entry = _entry(**{CONF_WC_DEVICE_ID: DEVICE})
    await _setup(hass, entry)
    assert created_clients and not created_clients[-1].is_closed
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert created_clients[-1].is_closed


async def test_ims_only_creates_no_session(hass: HomeAssistant, created_clients) -> None:
    coordinator = await _setup(hass, _entry())
    assert created_clients == []
    assert coordinator.data.current["temperature"] == 18.0


async def _submit_user(hass: HomeAssistant, flow_id: str | None = None, **user):
    if flow_id is None:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        assert result["step_id"] == "user"
        flow_id = result["flow_id"]
    return await hass.config_entries.flow.async_configure(
        flow_id, {CONF_LANGUAGE: "en", **user}
    )


async def test_flow_bad_password_can_be_fixed_in_place(hass: HomeAssistant, created_clients) -> None:
    creds = {CONF_WC_DEVICE_ID: DEVICE, CONF_WC_USERNAME: "me"}
    result = await _submit_user(hass, **creds, **{CONF_WC_PASSWORD: "wrong"})
    # The error is shown on the form that has the password field.
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "weathercloud_auth"}
    assert all(c.is_closed for c in created_clients)

    result = await _submit_user(hass, result["flow_id"], **creds, **{CONF_WC_PASSWORD: "secret"})
    assert result["step_id"] == "city"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_CITY: "2"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_WC_PASSWORD] == "secret"


async def test_flow_bad_station(hass: HomeAssistant, server) -> None:
    server.fail_values_with = 404
    result = await _submit_user(hass, **{CONF_WC_DEVICE_ID: DEVICE})
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "weathercloud_invalid"}


async def test_flow_ims_only(hass: HomeAssistant, created_clients) -> None:
    result = await _submit_user(hass)
    assert result["step_id"] == "city"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_CITY: "2"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_WC_DEVICE_ID not in result["data"]
    assert created_clients == []


# --- reauth ---------------------------------------------------------------
async def test_rejected_login_starts_reauth(hass: HomeAssistant, server) -> None:
    entry = _entry(**{CONF_WC_DEVICE_ID: DEVICE, CONF_WC_USERNAME: "me", CONF_WC_PASSWORD: "old"})
    coordinator = await _setup(hass, entry)
    # Public data still works, only the login is missing.
    assert coordinator.data.weathercloud_online
    assert coordinator.data.current["temperature"] == 21.4

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1 and flows[0]["context"]["source"] == SOURCE_REAUTH
    assert flows[0]["step_id"] == "reauth_confirm"

    # A second poll does not open another prompt or retry the bad password.
    await coordinator.async_force_refresh()
    await hass.async_block_till_done()
    assert len(hass.config_entries.flow.async_progress_by_handler(DOMAIN)) == 1
    assert server.logins == 1

    # Wrong again -> error on the form.
    result = await hass.config_entries.flow.async_configure(
        flows[0]["flow_id"], {CONF_WC_USERNAME: "me", CONF_WC_PASSWORD: "nope"}
    )
    assert result["errors"] == {"base": "weathercloud_auth"}

    # Right password -> saved, entry reloaded, indoor sensors back.
    result = await hass.config_entries.flow.async_configure(
        flows[0]["flow_id"], {CONF_WC_USERNAME: "me", CONF_WC_PASSWORD: "secret"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    await hass.async_block_till_done()
    assert entry.data[CONF_WC_PASSWORD] == "secret"
    assert hass.data[DOMAIN][entry.entry_id].data.current["inside_temperature"] == 24.0


async def test_reauth_can_drop_the_login(hass: HomeAssistant) -> None:
    entry = _entry(**{CONF_WC_DEVICE_ID: DEVICE, CONF_WC_USERNAME: "me", CONF_WC_PASSWORD: "old"})
    await _setup(hass, entry)
    flow = hass.config_entries.flow.async_progress_by_handler(DOMAIN)[0]
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {})
    assert result["reason"] == "reauth_successful"
    await hass.async_block_till_done()
    assert CONF_WC_USERNAME not in entry.data and CONF_WC_PASSWORD not in entry.data
    assert entry.data[CONF_WC_DEVICE_ID] == DEVICE


# --- reconfigure ----------------------------------------------------------
async def _reconfigure(hass: HomeAssistant, entry: MockConfigEntry, user: dict):
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user)
    await hass.async_block_till_done()
    return result


async def test_reconfigure_add_station_and_login(hass: HomeAssistant) -> None:
    entry = _entry()
    await _setup(hass, entry)
    result = await _reconfigure(
        hass, entry,
        {CONF_WC_DEVICE_ID: DEVICE, CONF_WC_USERNAME: "me", CONF_WC_PASSWORD: "secret"},
    )
    assert result["reason"] == "reconfigure_successful"
    assert entry.unique_id == f"2_{DEVICE}"
    assert hass.data[DOMAIN][entry.entry_id].data.current["inside_temperature"] == 24.0


async def test_reconfigure_empty_password_keeps_saved_one(hass: HomeAssistant) -> None:
    entry = _entry(**{CONF_WC_DEVICE_ID: DEVICE, CONF_WC_USERNAME: "me", CONF_WC_PASSWORD: "secret"})
    await _setup(hass, entry)
    result = await _reconfigure(
        hass, entry, {CONF_WC_DEVICE_ID: DEVICE, CONF_WC_USERNAME: "me"}
    )
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_WC_PASSWORD] == "secret"


async def test_reconfigure_back_to_ims_only(hass: HomeAssistant, created_clients) -> None:
    entry = _entry(**{CONF_WC_DEVICE_ID: DEVICE, CONF_WC_USERNAME: "me", CONF_WC_PASSWORD: "secret"})
    await _setup(hass, entry)
    result = await _reconfigure(hass, entry, {})
    assert result["reason"] == "reconfigure_successful"
    assert not {CONF_WC_DEVICE_ID, CONF_WC_USERNAME, CONF_WC_PASSWORD} & set(entry.data)
    assert entry.unique_id == "2_ims_only"
    assert hass.data[DOMAIN][entry.entry_id].data.weathercloud_online is False
    assert all(c.is_closed for c in created_clients)  # old session released


async def test_reconfigure_rejects_bad_password(hass: HomeAssistant) -> None:
    entry = _entry(**{CONF_WC_DEVICE_ID: DEVICE})
    await _setup(hass, entry)
    result = await _reconfigure(
        hass, entry, {CONF_WC_DEVICE_ID: DEVICE, CONF_WC_USERNAME: "me", CONF_WC_PASSWORD: "x"}
    )
    assert result["errors"] == {"base": "weathercloud_auth"}
    assert CONF_WC_USERNAME not in entry.data


async def test_reconfigure_duplicate_is_refused(hass: HomeAssistant) -> None:
    other = MockConfigEntry(
        domain=DOMAIN, data={CONF_CITY: "2", CONF_LANGUAGE: "en", CONF_WC_DEVICE_ID: "999"},
        unique_id="2_999",
    )
    other.add_to_hass(hass)
    entry = _entry()
    await _setup(hass, entry)
    result = await _reconfigure(hass, entry, {CONF_WC_DEVICE_ID: "999"})
    assert result["errors"] == {"base": "already_configured"}


# --- diagnostics ----------------------------------------------------------
@pytest.mark.skipif(get_diagnostics_for_config_entry is None, reason="old test harness")
async def test_diagnostics_redacts_login(hass: HomeAssistant, hass_client) -> None:
    entry = _entry(**{CONF_WC_DEVICE_ID: DEVICE, CONF_WC_USERNAME: "me@x.com", CONF_WC_PASSWORD: "secret"})
    await _setup(hass, entry)
    diag = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    text = str(diag)
    assert "secret" not in text and "me@x.com" not in text
    assert diag["entry"]["data"][CONF_WC_PASSWORD] == "**REDACTED**"
    assert diag["weathercloud_session"]["logged_in"] is True
    assert diag["libraries"]["weathercloud"].startswith("1.")
    assert diag["data"]["current"]["temperature"] == 21.4
    assert diag["data"]["station"]["name"] == "Rooftop Ramat Aviv"
    assert diag["data"]["station"]["latitude"] == "**REDACTED**"
    assert "32.1133" not in text



# --- station position -----------------------------------------------------
def _weather_state(hass: HomeAssistant, entry: MockConfigEntry):
    entity_id = er.async_get(hass).async_get_entity_id(
        "weather", DOMAIN, f"{entry.entry_id}_weather"
    )
    return hass.states.get(entity_id)


async def test_station_on_map(hass: HomeAssistant, server) -> None:
    entry = _entry(**{CONF_WC_DEVICE_ID: DEVICE})
    coordinator = await _setup(hass, entry)
    attrs = _weather_state(hass, entry).attributes
    assert attrs["latitude"] == 32.1133 and attrs["longitude"] == 34.8044
    assert attrs["station_name"] == "Rooftop Ramat Aviv"
    assert attrs["station_city"] == "Tel Aviv-Yafo"
    assert attrs["station_altitude"] == 35.0

    # Fetched once per load, not on every refresh.
    pages = server.paths.count(f"/d{DEVICE}")
    await coordinator.async_force_refresh()
    await hass.async_block_till_done()
    assert server.paths.count(f"/d{DEVICE}") == pages == 1


async def test_station_position_can_be_hidden(hass: HomeAssistant) -> None:
    entry = _entry(**{CONF_WC_DEVICE_ID: DEVICE})
    await _setup(hass, entry)
    hass.config_entries.async_update_entry(entry, options={CONF_STATION_LOCATION: False})
    await hass.async_block_till_done()
    attrs = _weather_state(hass, entry).attributes
    assert "latitude" not in attrs and "longitude" not in attrs
    assert attrs["station_name"] == "Rooftop Ramat Aviv"


async def test_station_details_failure_is_harmless(hass: HomeAssistant, server) -> None:
    server.fail_info = server.fail_page = True
    entry = _entry(**{CONF_WC_DEVICE_ID: DEVICE})
    coordinator = await _setup(hass, entry)
    assert coordinator.data.weathercloud_online
    assert coordinator.data.current["temperature"] == 21.4
    assert "latitude" not in _weather_state(hass, entry).attributes


async def test_ims_only_has_no_station_attributes(hass: HomeAssistant) -> None:
    entry = _entry()
    await _setup(hass, entry)
    attrs = _weather_state(hass, entry).attributes
    assert "station_name" not in attrs and "latitude" not in attrs


async def test_options_show_station_toggle_only_with_station(hass: HomeAssistant) -> None:
    with_station = _entry(**{CONF_WC_DEVICE_ID: DEVICE})
    await _setup(hass, with_station)
    form = await hass.config_entries.options.async_init(with_station.entry_id)
    assert CONF_STATION_LOCATION in form["data_schema"].schema

    ims_only = MockConfigEntry(
        domain=DOMAIN, data={CONF_CITY: "3", CONF_LANGUAGE: "en"}, unique_id="3_ims_only"
    )
    await _setup(hass, ims_only)
    form = await hass.config_entries.options.async_init(ims_only.entry_id)
    assert CONF_STATION_LOCATION not in form["data_schema"].schema
