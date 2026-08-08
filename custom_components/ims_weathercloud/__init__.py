"""IMS + Weathercloud merged integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CITY,
    CONF_CUSTOM_ICONS,
    CONF_ICONS_TARGET,
    CONF_IMS_INTERVAL,
    CONF_LANGUAGE,
    CONF_WC_DEVICE_ID,
    CONF_WC_INTERVAL,
    CONF_WC_PASSWORD,
    CONF_WC_USERNAME,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import ImsWeathercloudCoordinator
from .dependency_logging import remove_dependency_logging, setup_dependency_logging
from .theme_installer import (
    async_apply_icons,
    async_register_icon_path,
    async_remove_icons,
)

_RELOAD_KEYS = (
    CONF_CITY,
    CONF_LANGUAGE,
    CONF_WC_DEVICE_ID,
    CONF_WC_USERNAME,
    CONF_WC_PASSWORD,
    CONF_IMS_INTERVAL,
    CONF_WC_INTERVAL,
)


def _reload_signature(entry: ConfigEntry) -> tuple:
    merged = {**entry.data, **entry.options}
    return tuple(merged.get(key) for key in _RELOAD_KEYS)


def _icons_state(entry: ConfigEntry) -> tuple[bool, str]:
    on = entry.options.get(CONF_CUSTOM_ICONS, entry.data.get(CONF_CUSTOM_ICONS, False))
    target = entry.options.get(CONF_ICONS_TARGET, entry.data.get(CONF_ICONS_TARGET, ""))
    return bool(on), target


async def _async_apply_icons_state(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply or remove the custom-icon theme (all I/O off-loop, non-blocking)."""
    on, target = _icons_state(entry)
    if on:
        await async_apply_icons(hass, target)
    else:
        await async_remove_icons(hass, target)


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

    store = hass.data.setdefault(DOMAIN, {})
    store[entry.entry_id] = coordinator
    store[f"{entry.entry_id}_sig"] = _reload_signature(entry)

    await async_register_icon_path(hass)
    entry.async_create_background_task(
        hass, _async_apply_icons_state(hass, entry), "ims_wc_apply_icons"
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        store = hass.data[DOMAIN]
        store.pop(entry.entry_id, None)
        store.pop(f"{entry.entry_id}_sig", None)
        remove_dependency_logging(entry.entry_id)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    store = hass.data.get(DOMAIN, {})
    old_sig = store.get(f"{entry.entry_id}_sig")
    new_sig = _reload_signature(entry)

    if new_sig != old_sig:
        await hass.config_entries.async_reload(entry.entry_id)
        return

    # icon-only change -> apply in the background
    entry.async_create_background_task(
        hass, _async_apply_icons_state(hass, entry), "ims_wc_apply_icons"
    )
