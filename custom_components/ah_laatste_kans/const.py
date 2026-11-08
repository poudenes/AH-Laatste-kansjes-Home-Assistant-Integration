"""Constants for the AH Laatste Kans integration."""

from __future__ import annotations

DOMAIN = "ah_laatste_kans"
VERSION = "0.1.1"

CONF_COUNTRY = "country"
CONF_TOKENS = "tokens"
CONF_CODE = "code"
CONF_POSTCODE = "postcode"
CONF_STORE_COUNT = "store_count"
CONF_STORES = "stores"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_KEYWORDS = "keywords"

DEFAULT_COUNTRY = "NL"
DEFAULT_STORE_COUNT = 5
DEFAULT_SCAN_INTERVAL = 30  # minutes
MIN_SCAN_INTERVAL = 15

# Fired for every Laatste Kans product that was not there at the previous update.
EVENT_NEW_BARGAIN = f"{DOMAIN}_new_bargain"

CARD_URL = f"/{DOMAIN}/ah-laatste-kans-card.js"

COUNTRIES: dict[str, dict[str, str]] = {
    "NL": {
        "name": "Nederland",
        "api": "https://api.ah.nl",
        "login": "https://login.ah.nl",
        "client_id": "appie-ios",
        "application": "AHWEBSHOP",
        "webshop": "https://www.ah.nl",
    },
    "BE": {
        "name": "België",
        "api": "https://api.ah.be",
        "login": "https://login.ah.be",
        "client_id": "appie-be-ios",
        "application": "AHBEWEBSHOP",
        "webshop": "https://www.ah.be",
    },
}
