"""Fetches the Laatste Kans products of the selected stores."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import AHApi, AHAuthError, AHConnectionError, AHError, store_label
from .const import (
    CONF_KEYWORDS,
    CONF_SCAN_INTERVAL,
    CONF_STORES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_NEW_BARGAIN,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

type AHConfigEntry = ConfigEntry[AHCoordinator]


def parse_keywords(text: str | None) -> list[str]:
    """'zalm, Ben & Jerry, kaas' -> ['zalm', 'Ben & Jerry', 'kaas']."""
    return [k.strip() for k in (text or "").replace("\n", ",").split(",") if k.strip()]


def notified_store_key(entry_id: str) -> str:
    return f"{DOMAIN}.{entry_id}.notified"


def item_key(store_id: str, item: dict[str, Any]) -> str:
    """Identifies one sticker batch, to know which products are new."""
    return f"{store_id}|{item['product_id']}|{item['expires']}|{item['discount']}"


class AHCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """One coordinator per config entry: all selected stores in one go."""

    config_entry: AHConfigEntry

    def __init__(self, hass: HomeAssistant, entry: AHConfigEntry, api: AHApi) -> None:
        minutes = max(MIN_SCAN_INTERVAL, int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)))
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=minutes),
        )
        self.api = api
        # Options as they were at setup: a change means "reload", a token update does not.
        self.options_snapshot = dict(entry.options)
        self._images: dict[int, str] = {}
        self._seen: set[str] | None = None
        # Watchlist matches that already fired an event; kept on disk so a restart does not notify again.
        self._notified_store: Store[list[str]] = Store(hass, 1, notified_store_key(entry.entry_id))
        self._notified: set[str] | None = None

    @property
    def stores(self) -> dict[str, dict[str, str]]:
        return dict(self.config_entry.options.get(CONF_STORES, {}))

    @property
    def keywords(self) -> list[str]:
        return parse_keywords(self.config_entry.options.get(CONF_KEYWORDS))

    async def _async_update_data(self) -> dict[str, Any]:
        if self._notified is None:
            self._notified = set(await self._notified_store.async_load() or [])
        stores = self.stores
        semaphore = asyncio.Semaphore(3)  # at most 3 stores at the same time: be nice to AH

        async def fetch(store_id: str) -> tuple[str, list[dict[str, Any]] | None, AHError | None]:
            async with semaphore:
                try:
                    return store_id, await self.api.bargains(store_id), None
                except AHError as err:
                    return store_id, None, err

        results = await asyncio.gather(*(fetch(sid) for sid in stores))
        errors = [err for _, items, err in results if err is not None]
        if stores and len(errors) == len(stores):
            if any(isinstance(e, AHAuthError) for e in errors):
                raise ConfigEntryAuthFailed("AH wil dat je opnieuw inlogt")
            raise UpdateFailed(f"Geen enkele winkel kon worden opgehaald: {errors[0]}")

        previous = (self.data or {}).get("stores", {})
        data_stores: dict[str, dict[str, Any]] = {}
        for store_id, items, err in results:
            if err is not None:
                _LOGGER.warning("Winkel %s ophalen mislukt: %s", store_id, err)
                # Keep the last known list, but say it is stale.
                old = previous.get(store_id, {})
                data_stores[store_id] = {"items": old.get("items", []), "error": str(err)}
            else:
                data_stores[store_id] = {"items": items or [], "error": None}

        await self._add_images(data_stores)
        self._fire_new_bargain_events(data_stores)

        return {
            "stores": data_stores,
            "updated": dt_util.utcnow().isoformat(),
            "watch": self._watch_matches(data_stores),
        }

    async def _add_images(self, data_stores: dict[str, dict[str, Any]]) -> None:
        ids = {i["product_id"] for s in data_stores.values() for i in s["items"] if i["product_id"]}
        missing = [pid for pid in ids if pid not in self._images]
        if missing:
            try:
                self._images.update(await self.api.product_images(missing))
            except AHError as err:  # pictures are a nice-to-have
                _LOGGER.debug("Plaatjes ophalen mislukt: %s", err)
        for store in data_stores.values():
            for item in store["items"]:
                item["image"] = self._images.get(item["product_id"])

    def _fire_new_bargain_events(self, data_stores: dict[str, dict[str, Any]]) -> None:
        """Fire an event for every new product, and once for every watchlist match.

        After a start everything already on the shelf counts as known, so there is no flood of events,
        except watchlist matches that were never reported: those fire once (also after a restart,
        thanks to the list on disk), so a freshly saved watchlist reports what is there right now.
        """
        keys = {item_key(sid, i) for sid, s in data_stores.items() for i in s["items"]}
        first = self._seen is None
        notified = set(self._notified or ())
        keywords = [k.lower() for k in self.keywords]
        stores = self.stores
        for sid, store in data_stores.items():
            for item in store["items"]:
                key = item_key(sid, item)
                text = f"{item['title']} {item['brand']}".lower()
                hits = [k for k in keywords if k in text]
                is_new = not first and key not in self._seen
                if not is_new and not (hits and key not in notified):
                    continue
                if hits:
                    notified.add(key)
                self.hass.bus.async_fire(
                    EVENT_NEW_BARGAIN,
                    {
                        "store_id": sid,
                        "store": store_label(stores.get(sid, {"id": sid})),
                        "title": item["title"],
                        "brand": item["brand"],
                        "discount": item["discount"],
                        "price": item["price"],
                        "was": item["was"],
                        "stock": item["stock"],
                        "expires": item["expires"],
                        "image": item["image"],
                        "url": item["url"],
                        "watched": bool(hits),
                        "matched_keywords": hits,
                    },
                )
        self._seen = keys
        # Forget products that are gone, so the list on disk stays small
        # (but not those of a store that could not be fetched this time).
        failed = {sid for sid, s in data_stores.items() if s["error"]}
        notified = {k for k in notified if k in keys or k.split("|", 1)[0] in failed}
        if notified != self._notified:
            self._notified = notified
            self._notified_store.async_delay_save(lambda: sorted(notified), 1)

    def _watch_matches(self, data_stores: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        keywords = [k.lower() for k in self.keywords]
        if not keywords:
            return []
        stores = self.stores
        matches = []
        for sid, store in data_stores.items():
            for item in store["items"]:
                text = f"{item['title']} {item['brand']}".lower()
                hits = [k for k in keywords if k in text]
                if hits:
                    matches.append({**item, "store_id": sid, "store": store_label(stores.get(sid, {"id": sid})), "keywords": hits})
        matches.sort(key=lambda i: -i["discount"])
        return matches
