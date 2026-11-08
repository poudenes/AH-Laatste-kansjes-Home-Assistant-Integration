"""Client for the (unofficial, undocumented) API of the Albert Heijn app.

Endpoints as documented by the community project github.com/gwillem/appie-go.
AH can change or block this API at any moment.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date
import logging
import re
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import aiohttp

from .const import COUNTRIES

_LOGGER = logging.getLogger(__name__)

USER_AGENT = "Appie/9.28 (iPhone17,3; iPhone; CPU OS 26_1 like Mac OS X)"
CLIENT_VERSION = "9.28"
TIMEOUT = aiohttp.ClientTimeout(total=30)

STORES_QUERY = """
query StoresSearch($filter: StoresFilterInput) {
  storesSearch(filter: $filter, limit: %d) {
    result { id name storeType address { street houseNumber houseNumberExtra postalCode city } }
  }
}
"""

BARGAINS_QUERY = """
query BargainItems($storeId: String!) {
  bargainItems(storeId: $storeId) {
    product { id title brand salesUnitSize }
    categoryTitle
    markdown { markdownType markdownExpirationDate markdownPercentage }
    stock
    bargainPrice { priceWas priceNow }
  }
}
"""


class AHError(Exception):
    """General API error."""


class AHAuthError(AHError):
    """The login is missing, expired or refused."""


class AHConnectionError(AHError):
    """AH could not be reached."""


def extract_code(text: str) -> str | None:
    """Get the login code from what the user pasted: the full appie:// URL, a log line, or just the code."""
    text = (text or "").strip().strip("'\"")
    match = re.search(r"appie://login-exit\?[^\s'\"]+", text)
    if match:
        text = match.group(0)
    if "code=" in text:
        query = urlparse(text).query or text.split("?", 1)[-1]
        codes = parse_qs(query).get("code")
        return codes[0] if codes else None
    if re.fullmatch(r"[A-Za-z0-9._~\-]{8,}", text):
        return text
    return None


def login_url(country: str) -> str:
    """URL of AH's own login page (the user logs in there, including the 6-digit code)."""
    cfg = COUNTRIES[country]
    return (
        f"{cfg['login']}/login?client_id={cfg['client_id']}"
        "&response_type=code&redirect_uri=appie://login-exit"
    )


def _num(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", ".").strip())
    except ValueError:
        return None


def _best_image(images: list[dict[str, Any]] | None) -> str | None:
    best: tuple[int, str] | None = None
    for img in images or []:
        url = img.get("url")
        if not url:
            continue
        width = int(_num(img.get("width")) or 400)
        score = abs(width - 400)
        if best is None or score < best[0]:
            best = (score, url)
    return best[1] if best else None


def parse_store(raw: dict[str, Any]) -> dict[str, str]:
    """Turn a storesSearch result into the dict we keep in the config entry."""
    addr = raw.get("address") or {}
    number = str(addr.get("houseNumber") or "")
    if addr.get("houseNumberExtra"):
        number += f" {addr['houseNumberExtra']}"
    return {
        "id": str(raw.get("id")),
        "name": raw.get("name") or "Albert Heijn",
        "store_type": raw.get("storeType") or "",
        "street": addr.get("street") or "",
        "house_number": number,
        "postal_code": addr.get("postalCode") or "",
        "city": addr.get("city") or "",
    }


def store_label(store: dict[str, str]) -> str:
    """Human-readable name of a store, e.g. 'AH Vondellaan 200, Utrecht'."""
    street = f"{store.get('street', '')} {store.get('house_number', '')}".strip()
    city = store.get("city", "")
    if street and city:
        return f"AH {street}, {city}"
    return f"AH {street or city or store.get('name', store.get('id', ''))}"


class AHApi:
    """Async client. Keeps the tokens and refreshes them when needed."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        country: str,
        tokens: dict[str, Any] | None = None,
        token_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._session = session
        self.country = country
        self._cfg = COUNTRIES[country]
        self._tokens: dict[str, Any] = dict(tokens or {})
        self._token_callback = token_callback
        self._lock = asyncio.Lock()

    @property
    def tokens(self) -> dict[str, Any]:
        return dict(self._tokens)

    def _headers(self, auth: bool) -> dict[str, str]:
        headers = {
            "User-Agent": USER_AGENT,
            "x-client-name": self._cfg["client_id"],
            "x-client-version": CLIENT_VERSION,
            "x-application": self._cfg["application"],
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if auth and self._tokens.get("access_token"):
            headers["Authorization"] = f"Bearer {self._tokens['access_token']}"
        return headers

    # ---- tokens ----

    def _store_tokens(self, data: dict[str, Any]) -> None:
        if not data.get("access_token"):
            raise AHAuthError("AH gaf geen toegangstoken terug")
        self._tokens["access_token"] = data["access_token"]
        if data.get("refresh_token"):
            self._tokens["refresh_token"] = data["refresh_token"]
        if data.get("member_id"):
            self._tokens["member_id"] = str(data["member_id"])
        expires_in = _num(data.get("expires_in")) or 3600
        self._tokens["expires_at"] = time.time() + expires_in - 60
        if self._token_callback:
            self._token_callback(self.tokens)

    async def exchange_code(self, code: str) -> dict[str, Any]:
        """Trade the one-time login code for tokens."""
        try:
            data = await self._request(
                "POST",
                "/mobile-auth/v1/auth/token",
                json={"clientId": self._cfg["client_id"], "code": code},
                auth=False,
            )
        except AHConnectionError:
            raise
        except AHError as err:
            raise AHAuthError(f"Code geweigerd: {err}") from err
        self._store_tokens(data)
        return self.tokens

    async def _refresh(self) -> None:
        refresh_token = self._tokens.get("refresh_token")
        if not refresh_token:
            raise AHAuthError("Geen refresh-token; opnieuw inloggen nodig")
        try:
            data = await self._request(
                "POST",
                "/mobile-auth/v1/auth/token/refresh",
                json={"clientId": self._cfg["client_id"], "refreshToken": refresh_token},
                auth=False,
            )
        except AHConnectionError:
            raise
        except AHError as err:
            raise AHAuthError(f"Token verversen mislukt: {err}") from err
        self._store_tokens(data)

    async def _ensure_token(self, force: bool = False) -> None:
        async with self._lock:
            expired = time.time() >= float(self._tokens.get("expires_at") or 0)
            if force or not self._tokens.get("access_token") or expired:
                await self._refresh()

    # ---- HTTP ----

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: list[tuple[str, str]] | None = None,
        auth: bool = True,
        retry: bool = True,
    ) -> Any:
        if auth:
            await self._ensure_token()
        url = self._cfg["api"] + path
        try:
            async with self._session.request(
                method, url, json=json, params=params, headers=self._headers(auth), timeout=TIMEOUT
            ) as resp:
                status = resp.status
                if status < 400:
                    return await resp.json(content_type=None)
                body = (await resp.text())[:300]
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise AHConnectionError(f"AH niet bereikbaar: {err}") from err

        if auth and status in (401, 403):
            if retry:
                await self._ensure_token(force=True)
                return await self._request(method, path, json=json, params=params, auth=auth, retry=False)
            raise AHAuthError(f"HTTP {status}")
        raise AHError(f"HTTP {status}: {body}")

    async def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        data = await self._request("POST", "/graphql", json={"query": query, "variables": variables})
        errors = (data or {}).get("errors") or []
        if errors:
            msg = "; ".join(str(e.get("message", "")) for e in errors) or "onbekende fout"
            low = msg.lower()
            # AH hides the reason ("Subgraph errors redacted"); for bargainItems that means: not logged in.
            if "redacted" in low or "unauthor" in low or "authent" in low or "forbidden" in low:
                raise AHAuthError(msg)
            raise AHError(msg)
        return (data or {}).get("data") or {}

    # ---- endpoints ----

    async def search_stores(self, postcode: str, limit: int) -> list[dict[str, str]]:
        limit = max(1, min(int(limit), 25))
        pc = postcode.replace(" ", "").upper()
        data = await self.graphql(STORES_QUERY % limit, {"filter": {"postalCode": pc}})
        results = ((data.get("storesSearch") or {}).get("result")) or []
        return [parse_store(r) for r in results if r.get("id") is not None]

    async def bargains(self, store_id: str) -> list[dict[str, Any]]:
        data = await self.graphql(BARGAINS_QUERY, {"storeId": str(store_id)})
        items: list[dict[str, Any]] = []
        for raw in data.get("bargainItems") or []:
            product = raw.get("product") or {}
            markdown = raw.get("markdown") or {}
            price = raw.get("bargainPrice") or {}
            now, was = _num(price.get("priceNow")), _num(price.get("priceWas"))
            pid = int(_num(product.get("id")) or 0)
            items.append(
                {
                    "product_id": pid,
                    "title": product.get("title") or "Onbekend product",
                    "brand": product.get("brand") or "",
                    "unit": product.get("salesUnitSize") or "",
                    "category": raw.get("categoryTitle") or "Overig",
                    "discount": round(_num(markdown.get("markdownPercentage")) or 0),
                    "price": now,
                    "was": was,
                    "stock": int(_num(raw.get("stock")) or 0),
                    "expires": (markdown.get("markdownExpirationDate") or "")[:10],
                    "image": None,
                    "url": f"{self._cfg['webshop']}/producten/product/wi{pid}" if pid else None,
                }
            )
        items.sort(key=lambda i: (-i["discount"], i["title"]))
        return items

    async def product_images(self, ids: list[int]) -> dict[int, str]:
        """Picture URL per product id (max 30 ids per call)."""
        result: dict[int, str] = {}
        for start in range(0, len(ids), 30):
            chunk = ids[start : start + 30]
            params = [("ids", str(i)) for i in chunk] + [("sortOn", "INPUT_PRODUCT_IDS")]
            data = await self._request("GET", "/mobile-services/product/search/v2/products", params=params)
            for product in data or []:
                pid = int(_num(product.get("webshopId")) or 0)
                url = _best_image(product.get("images"))
                if pid and url:
                    result[pid] = url
        return result


def days_left(expires: str) -> int | None:
    """Days until the best-before date (0 = today)."""
    try:
        return (date.fromisoformat(expires) - date.today()).days
    except (TypeError, ValueError):
        return None
