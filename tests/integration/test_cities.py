"""The locality list comes only from IMS: no bundled fallback list."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ims_weathercloud import const
from custom_components.ims_weathercloud.config_flow import (
    IMS_LOCATIONS_URL,
    _fetch_localized_cities,  # the real one, taken before any patching
)
from custom_components.ims_weathercloud.const import (
    CONF_CITY,
    CONF_LANGUAGE,
    DEFAULT_NAME,
    DOMAIN,
    locality_name,
)

PKG = "custom_components.ims_weathercloud"
HE_URL = IMS_LOCATIONS_URL.format(lang="he")
EN_URL = IMS_LOCATIONS_URL.format(lang="en")


def test_bundled_list_is_gone() -> None:
    assert not hasattr(const, "IMS_CITIES")


# --- fetching the list ----------------------------------------------------
async def test_fetch_localized_list(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(HE_URL, json={"data": {
        "1": {"name": "ירושלים"}, "3": {"name": "חיפה"}, "7": {}}})
    assert await _fetch_localized_cities(hass, "he") == {
        "1": "ירושלים", "3": "חיפה", "7": "7"}


async def test_fetch_uses_chosen_language(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(EN_URL, json={"data": {"3": {"name": "Haifa"}}})
    assert await _fetch_localized_cities(hass, "en") == {"3": "Haifa"}
    assert str(aioclient_mock.mock_calls[0][1]) == EN_URL


@pytest.mark.parametrize(
    "response",
    [
        {"status": 500},
        {"exc": aiohttp.ClientError("down")},
        {"exc": TimeoutError()},
        {"json": {"data": {}}},
        {"json": {"error": "nope"}},
        {"json": ["not", "a", "dict"]},
        {"text": "<html>maintenance</html>"},
    ],
)
async def test_fetch_failure_returns_empty(hass: HomeAssistant, aioclient_mock, response) -> None:
    aioclient_mock.get(HE_URL, **response)
    assert await _fetch_localized_cities(hass, "he") == {}


# --- the setup flow -------------------------------------------------------
@pytest.fixture
def no_real_setup():
    with (
        patch(f"{PKG}.config_flow._validate_ims", return_value=None),
        patch(f"{PKG}.async_setup_entry", return_value=True),
    ):
        yield


async def test_flow_list_unavailable_then_retry(hass: HomeAssistant, no_real_setup) -> None:
    with patch(
        f"{PKG}.config_flow._fetch_localized_cities",
        side_effect=[{}, {"3": "חיפה", "1": "ירושלים"}],
    ) as fetch:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_LANGUAGE: "he"}
        )
        # No made-up list: the user is told and stays on the same form.
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"
        assert result["errors"] == {"base": "ims_cities_unavailable"}

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_LANGUAGE: "he"}
        )
        assert result["step_id"] == "city"
        assert fetch.call_count == 2
        options = result["data_schema"].schema[CONF_CITY].config["options"]
        assert [o["label"] for o in options] == ["חיפה", "ירושלים"]

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CITY: "3"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"{DEFAULT_NAME} - חיפה"


async def test_flow_retry_uses_new_language(hass: HomeAssistant, no_real_setup) -> None:
    with patch(
        f"{PKG}.config_flow._fetch_localized_cities",
        side_effect=[{}, {"3": "Haifa"}],
    ) as fetch:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_LANGUAGE: "he"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_LANGUAGE: "en"}
        )
    assert result["step_id"] == "city"
    assert [c.args[1] for c in fetch.call_args_list] == ["he", "en"]


# --- device name without the list ----------------------------------------
@pytest.mark.parametrize(
    ("location", "title", "expected"),
    [
        ("תל אביב - יפו", f"{DEFAULT_NAME} - חיפה", "תל אביב - יפו"),
        (None, f"{DEFAULT_NAME} - חיפה", "חיפה"),
        ("", f"{DEFAULT_NAME} - Haifa", "Haifa"),
        (None, "My weather", "My weather"),
        (None, "", DEFAULT_NAME),
        (None, f"{DEFAULT_NAME} - ", DEFAULT_NAME),
    ],
)
def test_locality_name(location, title, expected) -> None:
    data = SimpleNamespace(location_name=location)
    assert locality_name(SimpleNamespace(title=title), data) == expected
    if location is None:
        assert locality_name(SimpleNamespace(title=title), None) == expected


async def test_device_named_from_title_when_ims_has_no_location(
    hass: HomeAssistant, device_registry: dr.DeviceRegistry
) -> None:
    current = SimpleNamespace(
        temperature=20.0, humidity=50, weather_code="1250", forecast_time=None,
        location=None,
    )
    entry = MockConfigEntry(
        domain=DOMAIN, title=f"{DEFAULT_NAME} - חיפה",
        data={CONF_CITY: "3", CONF_LANGUAGE: "he"}, unique_id="3_ims_only",
    )
    entry.add_to_hass(hass)
    with (
        patch(
            f"{PKG}.coordinator.ImsWeathercloudCoordinator._fetch_ims",
            return_value=(current, SimpleNamespace(days=[])),
        ),
        patch(f"{PKG}.async_register_icon_path", return_value=None),
        patch(f"{PKG}._async_apply_icons_state", return_value=None),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    assert [d.name for d in devices] == ["חיפה"]
