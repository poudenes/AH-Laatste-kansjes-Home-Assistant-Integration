"""Select entity: pick one store (or all) for the dashboard card.

The options follow the stores in the integration options; switching a store on or off reloads the
integration, so the list is always up to date. The choice survives a restart.
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .api import store_label
from .const import ALL_STORES, CONF_STORES
from .coordinator import AHConfigEntry
from .sensor import hub_device_info


async def async_setup_entry(
    hass: HomeAssistant, entry: AHConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([AHStoreSelect(entry)])


class AHStoreSelect(SelectEntity, RestoreEntity):
    """Which store the card shows: 'Alle winkels' or one store by name."""

    _attr_has_entity_name = True
    _attr_translation_key = "winkel"
    _attr_icon = "mdi:store-search-outline"

    def __init__(self, entry: AHConfigEntry) -> None:
        stores = entry.options.get(CONF_STORES, {})
        self._attr_unique_id = f"{entry.entry_id}_winkel"
        self._attr_device_info = hub_device_info(entry.entry_id)
        self._attr_options = [ALL_STORES, *(store_label(s) for s in stores.values())]
        self._attr_current_option = ALL_STORES

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        # A store that was switched off falls back to 'Alle winkels'.
        if last is not None and last.state in self._attr_options:
            self._attr_current_option = last.state

    async def async_select_option(self, option: str) -> None:
        self._attr_current_option = option
        self.async_write_ha_state()
