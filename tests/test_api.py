"""Tests for the HTTP layer against a fake AH."""

from __future__ import annotations

import time

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.ah_laatste_kans.api import AHApi, AHAuthError

BASE = "https://api.ah.nl"


async def test_exchange_refresh_and_bargains(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    saved = []
    aioclient_mock.post(f"{BASE}/mobile-auth/v1/auth/token",
                        json={"access_token": "a1", "refresh_token": "r1", "expires_in": 3600, "member_id": 7})
    aioclient_mock.post(f"{BASE}/graphql", json={"data": {"bargainItems": [
        {"product": {"id": 123, "title": "Brie", "brand": "AH", "salesUnitSize": "200 g"},
         "categoryTitle": "Kaas", "markdown": {"markdownExpirationDate": "2026-11-09", "markdownPercentage": "35"},
         "stock": "3", "bargainPrice": {"priceWas": "2.99", "priceNow": "1,94"}}]}})
    api = AHApi(async_get_clientsession(hass), "NL", token_callback=saved.append)

    tokens = await api.exchange_code("abc")
    assert tokens["access_token"] == "a1" and tokens["member_id"] == "7"
    assert saved and saved[-1]["refresh_token"] == "r1"

    items = await api.bargains("1868")
    assert items == [{
        "product_id": 123, "title": "Brie", "brand": "AH", "unit": "200 g", "category": "Kaas",
        "discount": 35, "price": 1.94, "was": 2.99, "stock": 3, "expires": "2026-11-09", "image": None,
        "url": "https://www.ah.nl/producten/product/wi123",
    }]
    sent = aioclient_mock.mock_calls[-1]
    assert sent[3]["Authorization"] == "Bearer a1"
    assert sent[3]["x-client-name"] == "appie-ios"


async def test_expired_token_is_refreshed(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(f"{BASE}/mobile-auth/v1/auth/token/refresh",
                        json={"access_token": "a2", "refresh_token": "r2", "expires_in": 3600})
    aioclient_mock.post(f"{BASE}/graphql", json={"data": {"storesSearch": {"result": [
        {"id": 1868, "name": "AH", "storeType": "REGULAR",
         "address": {"street": "Vondellaan", "houseNumber": 200, "postalCode": "3521GZ", "city": "Utrecht"}}]}}})
    api = AHApi(async_get_clientsession(hass), "NL",
                {"access_token": "old", "refresh_token": "r1", "expires_at": time.time() - 10})
    stores = await api.search_stores("3521 gz", 5)
    assert stores[0]["id"] == "1868" and stores[0]["house_number"] == "200"
    assert api.tokens["access_token"] == "a2"
    assert aioclient_mock.mock_calls[0][2] == {"clientId": "appie-ios", "refreshToken": "r1"}


async def test_redacted_error_is_auth_error(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(f"{BASE}/graphql", json={"data": {"bargainItems": None},
                                                 "errors": [{"message": "Subgraph errors redacted"}]})
    api = AHApi(async_get_clientsession(hass), "NL",
                {"access_token": "a", "refresh_token": "r", "expires_at": time.time() + 999})
    with pytest.raises(AHAuthError):
        await api.bargains("1868")


async def test_refused_code(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(f"{BASE}/mobile-auth/v1/auth/token", status=400, text="invalid_grant")
    api = AHApi(async_get_clientsession(hass), "NL")
    with pytest.raises(AHAuthError):
        await api.exchange_code("old")
