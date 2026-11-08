"""Sensors: one per store (state = number of products, the list in an attribute), a total and a watchlist."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import store_label
from .const import CONF_KEYWORDS, CONF_STORES, DOMAIN
from .coordinator import AHConfigEntry, AHCoordinator, parse_keywords

ATTRIBUTION = "Gegevens van Albert Heijn (onofficiële API)"


async def async_setup_entry(
    hass: HomeAssistant, entry: AHConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    stores: dict[str, dict[str, str]] = entry.options.get(CONF_STORES, {})
    entities: list[SensorEntity] = [AHStoreSensor(coordinator, store) for store in stores.values()]
    entities += [AHTotalSensor(coordinator), AHWatchlistSensor(coordinator)]
    async_add_entities(entities)


class AHBaseSensor(CoordinatorEntity[AHCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "producten"


class AHStoreSensor(AHBaseSensor):
    """Laatste Kans products in one store.

    The list can easily be 20+ KB, which is more than the recorder wants to store (16 KB),
    so it is excluded from the history; the dashboard still gets it live.
    """

    _attr_translation_key = "laatste_kans"
    _attr_icon = "mdi:clock-alert-outline"
    _unrecorded_attributes = frozenset({"items", "categories"})

    def __init__(self, coordinator: AHCoordinator, store: dict[str, str]) -> None:
        super().__init__(coordinator)
        self._store = store
        self._store_id = store["id"]
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{self._store_id}_laatste_kans"
        query = quote(f"Albert Heijn {store.get('street', '')} {store.get('house_number', '')} {store.get('city', '')}")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{self._store_id}")},
            name=store_label(store),
            manufacturer="Albert Heijn",
            model=(store.get("store_type") or "Supermarkt").title(),
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=f"https://www.google.com/maps/search/?api=1&query={query}",
        )

    @property
    def _data(self) -> dict[str, Any]:
        return ((self.coordinator.data or {}).get("stores") or {}).get(self._store_id) or {}

    @property
    def available(self) -> bool:
        return super().available and bool(self._data)

    @property
    def native_value(self) -> int | None:
        items = self._data.get("items")
        return None if items is None else len(items)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        items = self._data.get("items") or []
        return {
            "integration": DOMAIN,
            "store_id": self._store_id,
            "store": store_label(self._store),
            "address": f"{self._store.get('street', '')} {self._store.get('house_number', '')}".strip(),
            "postal_code": self._store.get("postal_code", ""),
            "city": self._store.get("city", ""),
            "best_discount": max((i["discount"] for i in items), default=0),
            "updated": (self.coordinator.data or {}).get("updated"),
            "error": self._data.get("error"),
            "categories": sorted({i["category"] for i in items}),
            "items": items,
        }


class AHHubSensor(AHBaseSensor):
    def __init__(self, coordinator: AHCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_hub")},
            name="AH Laatste Kans",
            manufacturer="Albert Heijn",
            model="Laatste Kans",
            entry_type=DeviceEntryType.SERVICE,
        )


class AHTotalSensor(AHHubSensor):
    """Total over all selected stores, with the 10 best deals."""

    _attr_translation_key = "totaal"
    _attr_icon = "mdi:cart-percent"
    _unrecorded_attributes = frozenset({"top"})

    def __init__(self, coordinator: AHCoordinator) -> None:
        super().__init__(coordinator, "totaal")

    @property
    def native_value(self) -> int:
        stores = (self.coordinator.data or {}).get("stores") or {}
        return sum(len(s.get("items") or []) for s in stores.values())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        stores = (self.coordinator.data or {}).get("stores") or {}
        names = self.coordinator.stores
        everything = [
            {**i, "store": store_label(names.get(sid, {"id": sid}))}
            for sid, s in stores.items()
            for i in s.get("items") or []
        ]
        everything.sort(key=lambda i: (-i["discount"], -((i["was"] or 0) - (i["price"] or 0))))
        return {
            "stores": len(stores),
            "updated": (self.coordinator.data or {}).get("updated"),
            "top": everything[:10],
        }


class AHWatchlistSensor(AHHubSensor):
    """Products matching the watchlist keywords (Options > Instellingen)."""

    _attr_translation_key = "volglijst"
    _attr_icon = "mdi:bell-ring-outline"
    _unrecorded_attributes = frozenset({"matches"})

    def __init__(self, coordinator: AHCoordinator) -> None:
        super().__init__(coordinator, "volglijst")

    @property
    def native_value(self) -> int:
        return len((self.coordinator.data or {}).get("watch") or [])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "keywords": parse_keywords(self.coordinator.config_entry.options.get(CONF_KEYWORDS)),
            "matches": (self.coordinator.data or {}).get("watch") or [],
        }
