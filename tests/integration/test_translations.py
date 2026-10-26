"""Every field on every form has a label, in each shipped language.

Loads the texts through Home Assistant's own translation loader, the same
path the UI uses, so a missing key here is a raw key on screen there.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations
from homeassistant.setup import async_setup_component

ROOT = Path(__file__).resolve().parents[2]
INTEGRATION = ROOT / "custom_components" / "ims_weathercloud"
DOMAIN = "ims_weathercloud"

LANGUAGES = sorted(p.stem for p in (INTEGRATION / "translations").glob("*.json"))

# Form fields per step, as the flows build them.
CONFIG_FIELDS = {
    "user": ["language", "wc_device_id", "wc_username", "wc_password",
             "ims_interval", "wc_interval", "custom_icons"],
    "city": ["city"],
    "reconfigure": ["wc_device_id", "wc_username", "wc_password"],
    "reauth_confirm": ["wc_username", "wc_password"],
}
OPTIONS_FIELDS = {
    "init": ["language", "ims_interval", "wc_interval", "custom_icons",
             "station_location"],
    "icons": ["icons_target"],
}
CONFIG_ERRORS = ["ims_invalid", "ims_cities_unavailable", "weathercloud_invalid",
                 "weathercloud_auth", "already_configured"]
CONFIG_ABORTS = ["already_configured", "reconfigure_successful", "reauth_successful"]


def test_languages_found() -> None:
    assert {"en", "he"} <= set(LANGUAGES)


def test_translation_files_match_strings_json() -> None:
    """translations/*.json must have the same keys as strings.json."""

    def keys(node, prefix=""):
        out = set()
        for k, v in node.items():
            path = f"{prefix}.{k}" if prefix else k
            out |= keys(v, path) if isinstance(v, dict) else {path}
        return out

    reference = keys(json.loads((INTEGRATION / "strings.json").read_text("utf-8")))
    for lang in LANGUAGES:
        found = keys(json.loads((INTEGRATION / "translations" / f"{lang}.json").read_text("utf-8")))
        assert not (reference - found), f"{lang}.json is missing {sorted(reference - found)}"
        assert not (found - reference), f"{lang}.json has extra {sorted(found - reference)}"


@pytest.mark.parametrize("language", LANGUAGES)
async def test_every_form_field_is_translated(hass: HomeAssistant, language: str) -> None:
    await async_setup_component(hass, "http", {})
    config = await async_get_translations(hass, language, "config", [DOMAIN])
    options = await async_get_translations(hass, language, "options", [DOMAIN])

    missing = []
    for step, fields in CONFIG_FIELDS.items():
        missing += [
            f"config.step.{step}.data.{f}" for f in fields
            if not config.get(f"component.{DOMAIN}.config.step.{step}.data.{f}")
        ]
        if not config.get(f"component.{DOMAIN}.config.step.{step}.title"):
            missing.append(f"config.step.{step}.title")
    missing += [
        f"config.error.{e}" for e in CONFIG_ERRORS
        if not config.get(f"component.{DOMAIN}.config.error.{e}")
    ]
    missing += [
        f"config.abort.{a}" for a in CONFIG_ABORTS
        if not config.get(f"component.{DOMAIN}.config.abort.{a}")
    ]
    for step, fields in OPTIONS_FIELDS.items():
        missing += [
            f"options.step.{step}.data.{f}" for f in fields
            if not options.get(f"component.{DOMAIN}.options.step.{step}.data.{f}")
        ]
    assert not missing, f"{language}: untranslated {missing}"
