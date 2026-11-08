"""AH Laatste Kans: Albert Heijn 'Laatste Kans' stickers per store in Home Assistant."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .api import AHApi
from .const import CARD_URL, CONF_COUNTRY, CONF_STORES, CONF_TOKENS, DOMAIN, VERSION
from .coordinator import AHConfigEntry, AHCoordinator, notified_store_key

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the Lovelace card and load it on every dashboard."""
    card = Path(__file__).parent / "frontend" / "ah-laatste-kans-card.js"
    await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(card), False)])
    add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: AHConfigEntry) -> bool:
    """Set up one AH account with its stores."""

    def save_tokens(tokens: dict[str, Any]) -> None:
        # Refreshed tokens are stored right away, so a restart does not need a new login.
        hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_TOKENS: tokens})

    api = AHApi(async_get_clientsession(hass), entry.data[CONF_COUNTRY], entry.data.get(CONF_TOKENS), save_tokens)
    coordinator = AHCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    _remove_deselected_stores(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AHConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: AHConfigEntry) -> None:
    """Clean up the list of already reported watchlist matches."""
    await Store(hass, 1, notified_store_key(entry.entry_id)).async_remove()


async def _async_entry_updated(hass: HomeAssistant, entry: AHConfigEntry) -> None:
    """Reload when the options change (stores, interval, watchlist); not when only the tokens are refreshed."""
    coordinator: AHCoordinator | None = getattr(entry, "runtime_data", None)
    if coordinator is None or dict(entry.options) != coordinator.options_snapshot:
        await hass.config_entries.async_reload(entry.entry_id)


def _remove_deselected_stores(hass: HomeAssistant, entry: AHConfigEntry) -> None:
    """A store that was switched off disappears with its device and sensor."""
    valid = {(DOMAIN, f"{entry.entry_id}_{sid}") for sid in entry.options.get(CONF_STORES, {})}
    valid.add((DOMAIN, f"{entry.entry_id}_hub"))
    registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        if not device.identifiers & valid:
            registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)
