"""Diagnostics download: Settings > Devices & services > IMS + Weathercloud > ⋮."""
from __future__ import annotations

from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_WC_PASSWORD, CONF_WC_USERNAME, DOMAIN

# Diagnostics files often end up in public issues: no login, no home position.
TO_REDACT = {CONF_WC_USERNAME, CONF_WC_PASSWORD, "latitude", "longitude"}


def _version(package: str) -> str | None:
    try:
        return version(package)
    except PackageNotFoundError:
        return None


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    result: dict[str, Any] = {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "libraries": {
            "weathercloud": _version("weathercloud"),
            "weatheril": _version("weatheril"),
        },
    }
    if coordinator is None:
        return result

    result["coordinator"] = {
        "last_update_success": coordinator.last_update_success,
        "update_interval": str(coordinator.update_interval),
    }
    api = coordinator.weathercloud_api
    if api is not None:
        result["weathercloud_session"] = api.diagnostics()
    if coordinator.data is not None:
        result["data"] = async_redact_data(asdict(coordinator.data), TO_REDACT)
    return result
