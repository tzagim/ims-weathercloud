"""Manual refresh button for the IMS + Weathercloud integration."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN, IMS_CITIES, ims_site_url
from .coordinator import ImsWeathercloudCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: ImsWeathercloudCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([RefreshButton(coordinator, entry)])


class RefreshButton(CoordinatorEntity[ImsWeathercloudCoordinator], ButtonEntity):
    """Force an immediate refresh of both sources (resets the poll timer)."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: ImsWeathercloudCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_refresh"
        self._attr_translation_key = "refresh"
        name = (
            getattr(coordinator.data, "location_name", None)
            or IMS_CITIES.get(str(entry.data.get("city")), DEFAULT_NAME)
        )
        url = getattr(coordinator.data, "station_url", None) or ims_site_url(
            entry.data.get("language")
        )
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": name,
            "manufacturer": "IMS + Weathercloud",
            "entry_type": "service",
            "configuration_url": url,
        }

    async def async_press(self) -> None:
        await self.coordinator.async_force_refresh()
