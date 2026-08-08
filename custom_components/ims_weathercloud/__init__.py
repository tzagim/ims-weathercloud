"""IMS + Weathercloud merged integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_CUSTOM_ICONS, CONF_ICONS_TARGET, DOMAIN, PLATFORMS
from .coordinator import ImsWeathercloudCoordinator
from .dependency_logging import remove_dependency_logging, setup_dependency_logging
from .theme_installer import (
    async_apply_icons,
    async_register_icon_path,
    async_remove_icons,
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    # Quiet the weatheril Loguru flood before the first fetch runs.
    setup_dependency_logging(entry.entry_id)

    coordinator = ImsWeathercloudCoordinator(hass, entry)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        remove_dependency_logging(entry.entry_id)
        raise

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Serve bundled weather icons and apply the custom-icon option.
    await async_register_icon_path(hass)
    icons_on = entry.options.get(
        CONF_CUSTOM_ICONS, entry.data.get(CONF_CUSTOM_ICONS, False)
    )
    icons_target = entry.options.get(
        CONF_ICONS_TARGET, entry.data.get(CONF_ICONS_TARGET, "")
    )
    if icons_on:
        await async_apply_icons(hass, icons_target)
    else:
        await async_remove_icons(hass, icons_target)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        remove_dependency_logging(entry.entry_id)
    return unload_ok


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
