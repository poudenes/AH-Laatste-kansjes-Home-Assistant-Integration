"""Tests for the AH Laatste Kans integration (AH itself is mocked)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events, async_fire_time_changed

from custom_components.ah_laatste_kans.api import AHAuthError, extract_code
from custom_components.ah_laatste_kans.const import DOMAIN, EVENT_NEW_BARGAIN

API = "custom_components.ah_laatste_kans.api.AHApi"

STORES = [
    {"id": "1868", "name": "AH", "store_type": "REGULAR", "street": "Vondellaan", "house_number": "200",
     "postal_code": "3521GZ", "city": "Utrecht"},
    {"id": "1500", "name": "AH", "store_type": "XL", "street": "Kanaalweg", "house_number": "1",
     "postal_code": "3526KL", "city": "Utrecht"},
]


def item(pid: int, title: str, discount: int, price: float, was: float, expires: str = "2026-11-09") -> dict[str, Any]:
    return {"product_id": pid, "title": title, "brand": "AH", "unit": "1 st", "category": "Zuivel",
            "discount": discount, "price": price, "was": was, "stock": 2, "expires": expires,
            "image": None, "url": f"https://www.ah.nl/producten/product/wi{pid}"}


BARGAINS = {
    "1868": [item(1, "Campina Volle yoghurt", 70, 0.59, 1.95), item(2, "AH Zalmfilet", 35, 3.89, 5.99)],
    "1500": [item(3, "AH Kokosbowl", 70, 1.77, 5.89)],
}


def tokens() -> dict[str, Any]:
    return {"access_token": "acc", "refresh_token": "ref", "member_id": "42", "expires_at": 9999999999}


@pytest.fixture
def mock_api():
    async def bargains(self, store_id):
        return [dict(i) for i in BARGAINS[store_id]]

    with (
        patch(f"{API}.exchange_code", AsyncMock(return_value=tokens())),
        patch(f"{API}.search_stores", AsyncMock(return_value=STORES)),
        patch(f"{API}.bargains", bargains),
        patch(f"{API}.product_images", AsyncMock(return_value={1: "https://img/1.png"})),
        patch(f"{API}.tokens", tokens()),
    ):
        yield


def make_entry(stores=STORES, keywords: str = "") -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="AH Laatste Kans (3521GZ)",
        unique_id="NL_42",
        data={"country": "NL", "tokens": tokens()},
        options={"postcode": "3521GZ", "stores": {s["id"]: s for s in stores}, "scan_interval": 30, "keywords": keywords},
    )


# ---------- login code parsing ----------

@pytest.mark.parametrize(
    "text,expected",
    [
        ("appie://login-exit?code=abc123DEF456", "abc123DEF456"),
        ("Failed to launch 'appie://login-exit?code=abc123DEF456&state=x' because the scheme does not have a registered handler.", "abc123DEF456"),
        ("  abc123DEF456  ", "abc123DEF456"),
        ("hallo", None),
        ("", None),
    ],
)
def test_extract_code(text, expected):
    assert extract_code(text) == expected


# ---------- config flow ----------

async def test_full_config_flow(hass: HomeAssistant, mock_api) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"country": "NL"})
    assert result["step_id"] == "login"
    assert "login.ah.nl/login?client_id=appie-ios" in result["description_placeholders"]["login_url"]

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"code": "nope"})
    assert result["errors"] == {"base": "invalid_code"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"code": "appie://login-exit?code=abcdefgh1234"}
    )
    assert result["step_id"] == "postcode"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"postcode": "3521 gz", "store_count": 5})
    assert result["step_id"] == "stores"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"stores": ["1868"]})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "AH Laatste Kans (3521GZ)"
    assert result["data"]["tokens"]["refresh_token"] == "ref"
    assert list(result["options"]["stores"]) == ["1868"]
    assert hass.states.get("sensor.ah_vondellaan_200_utrecht_laatste_kans").state == "2"


async def test_login_refused(hass: HomeAssistant) -> None:
    with patch(f"{API}.exchange_code", AsyncMock(side_effect=AHAuthError("x"))):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"country": "NL"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"code": "abcdefgh1234"})
    assert result["errors"] == {"base": "auth_failed"}


async def test_no_stores(hass: HomeAssistant, mock_api) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"country": "NL"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"code": "abcdefgh1234"})
    with patch(f"{API}.search_stores", AsyncMock(return_value=[])):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"postcode": "9999ZZ", "store_count": 5})
    assert result["errors"] == {"base": "no_stores"}


# ---------- sensors ----------

async def test_sensors(hass: HomeAssistant, mock_api) -> None:
    entry = make_entry(keywords="zalm, kokos")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    store = hass.states.get("sensor.ah_vondellaan_200_utrecht_laatste_kans")
    assert store.state == "2"
    attrs = store.attributes
    assert attrs["integration"] == DOMAIN
    assert attrs["store"] == "AH Vondellaan 200, Utrecht"
    assert attrs["best_discount"] == 70
    assert attrs["items"][0]["title"] == "Campina Volle yoghurt"
    assert attrs["items"][0]["image"] == "https://img/1.png"

    assert hass.states.get("sensor.ah_kanaalweg_1_utrecht_laatste_kans").state == "1"
    total = hass.states.get("sensor.ah_laatste_kans_laatste_kans_total")
    assert total.state == "3"
    assert len(total.attributes["top"]) == 3
    watch = hass.states.get("sensor.ah_laatste_kans_laatste_kans_watchlist")
    assert watch.state == "2"
    assert {m["title"] for m in watch.attributes["matches"]} == {"AH Zalmfilet", "AH Kokosbowl"}

    # The big lists are kept out of the recorder (they can be more than 16 KB).
    assert {"items", "categories"} <= set(store.state_info["unrecorded_attributes"])
    assert "matches" in watch.state_info["unrecorded_attributes"]
    ent = er.async_get(hass)
    reg = ent.async_get("sensor.ah_vondellaan_200_utrecht_laatste_kans")
    assert reg is not None and reg.config_entry_id == entry.entry_id


async def test_new_bargain_event(hass: HomeAssistant, mock_api) -> None:
    entry = make_entry(keywords="brie")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    events = async_capture_events(hass, EVENT_NEW_BARGAIN)

    BARGAINS["1868"].append(item(9, "Président Brie", 50, 1.50, 2.99))
    try:
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
    finally:
        BARGAINS["1868"].pop()

    assert len(events) == 1
    data = events[0].data
    assert data["title"] == "Président Brie"
    assert data["store"] == "AH Vondellaan 200, Utrecht"
    assert data["watched"] is True and data["matched_keywords"] == ["brie"]


# ---------- options: stores on/off ----------

async def test_options_switch_store_off(hass: HomeAssistant, mock_api) -> None:
    entry = make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    devices = dr.async_get(hass)
    assert len(dr.async_entries_for_config_entry(devices, entry.entry_id)) == 3  # 2 stores + hub

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "stores"})
    assert result["step_id"] == "stores"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"stores": ["1500"]})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert list(entry.options["stores"]) == ["1500"]
    assert hass.states.get("sensor.ah_vondellaan_200_utrecht_laatste_kans") is None
    assert hass.states.get("sensor.ah_kanaalweg_1_utrecht_laatste_kans").state == "1"
    assert len(dr.async_entries_for_config_entry(devices, entry.entry_id)) == 2


async def test_options_search_other_postcode(hass: HomeAssistant, mock_api) -> None:
    entry = make_entry(stores=STORES[:1])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "search"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"postcode": "3526KL", "store_count": 5})
    assert result["step_id"] == "stores"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"stores": ["1868", "1500"]})
    await hass.async_block_till_done()
    assert set(entry.options["stores"]) == {"1868", "1500"}
    assert entry.options["postcode"] == "3526KL"
    assert hass.states.get("sensor.ah_kanaalweg_1_utrecht_laatste_kans").state == "1"


async def test_options_settings(hass: HomeAssistant, mock_api) -> None:
    entry = make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "settings"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"scan_interval": 60, "keywords": "yoghurt"})
    await hass.async_block_till_done()
    assert entry.options["scan_interval"] == 60
    assert entry.runtime_data.update_interval == timedelta(minutes=60)
    assert hass.states.get("sensor.ah_laatste_kans_laatste_kans_watchlist").state == "1"


# ---------- token refresh does not reload; auth failure starts reauth ----------

async def test_token_update_does_not_reload(hass: HomeAssistant, mock_api) -> None:
    entry = make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    hass.config_entries.async_update_entry(entry, data={**entry.data, "tokens": {**tokens(), "access_token": "new"}})
    await hass.async_block_till_done()
    assert entry.runtime_data is coordinator
    assert entry.state is ConfigEntryState.LOADED


async def test_auth_failure_starts_reauth(hass: HomeAssistant, mock_api) -> None:
    entry = make_entry()
    entry.add_to_hass(hass)
    with patch(f"{API}.bargains", AsyncMock(side_effect=AHAuthError("redacted"))):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == config_entries.SOURCE_REAUTH for f in flows)

    flow = next(f for f in flows if f["context"]["source"] == config_entries.SOURCE_REAUTH)
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {"code": "abcdefgh1234"})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reauth_successful"
    assert entry.state is ConfigEntryState.LOADED


async def test_one_store_failing_keeps_others(hass: HomeAssistant, mock_api) -> None:
    entry = make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    async def flaky(self, store_id):
        if store_id == "1500":
            raise AHAuthError("redacted")
        return [dict(i) for i in BARGAINS[store_id]]

    with patch(f"{API}.bargains", flaky):
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
    st = hass.states.get("sensor.ah_kanaalweg_1_utrecht_laatste_kans")
    assert st.state == "1"  # last known list
    assert st.attributes["error"]
    assert hass.states.get("sensor.ah_vondellaan_200_utrecht_laatste_kans").state == "2"
