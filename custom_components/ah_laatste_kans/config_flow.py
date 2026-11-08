"""Config and options flow for AH Laatste Kans.

Login: AH's login page uses reCAPTCHA and a 6-digit code, so Home Assistant does not ask for a password.
The user logs in on AH's own page in a browser; at the end that page redirects to
appie://login-exit?code=…  The user pastes that URL (or only the code) here and HA trades it for tokens.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from .api import AHApi, AHAuthError, AHConnectionError, AHError, extract_code, login_url, store_label
from .const import (
    CONF_CODE,
    CONF_COUNTRY,
    CONF_KEYWORDS,
    CONF_POSTCODE,
    CONF_SCAN_INTERVAL,
    CONF_STORE_COUNT,
    CONF_STORES,
    CONF_TOKENS,
    COUNTRIES,
    DEFAULT_COUNTRY,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STORE_COUNT,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

STORE_COUNT_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=1, max=15, step=1, mode=NumberSelectorMode.SLIDER)
)


def _stores_selector(stores: dict[str, dict[str, str]]) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=[SelectOptionDict(value=sid, label=store_label(s)) for sid, s in stores.items()],
            multiple=True,
            mode=SelectSelectorMode.LIST,
        )
    )


class AHConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up AH Laatste Kans."""

    VERSION = 1

    def __init__(self) -> None:
        self._country = DEFAULT_COUNTRY
        self._api: AHApi | None = None
        self._postcode = ""
        self._found: dict[str, dict[str, str]] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> AHOptionsFlow:
        return AHOptionsFlow()

    # ---- step 1: country ----

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._country = user_input[CONF_COUNTRY]
            return await self.async_step_login()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_COUNTRY, default=DEFAULT_COUNTRY): SelectSelector(
                        SelectSelectorConfig(
                            options=[SelectOptionDict(value=k, label=v["name"]) for k, v in COUNTRIES.items()],
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    # ---- step 2: login with the code from AH's login page ----

    async def async_step_login(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            code = extract_code(user_input[CONF_CODE])
            if not code:
                errors["base"] = "invalid_code"
            else:
                api = AHApi(async_get_clientsession(self.hass), self._country)
                try:
                    tokens = await api.exchange_code(code)
                except AHAuthError:
                    errors["base"] = "auth_failed"
                except AHConnectionError:
                    errors["base"] = "cannot_connect"
                else:
                    if self.source == SOURCE_REAUTH:
                        entry = self._get_reauth_entry()
                        return self.async_update_reload_and_abort(
                            entry, data_updates={CONF_TOKENS: tokens}
                        )
                    member = tokens.get("member_id")
                    if member:
                        await self.async_set_unique_id(f"{self._country}_{member}")
                        self._abort_if_unique_id_configured()
                    self._api = api
                    return await self.async_step_postcode()

        return self.async_show_form(
            step_id="login",
            data_schema=vol.Schema({vol.Required(CONF_CODE): TextSelector(TextSelectorConfig(multiline=True))}),
            errors=errors,
            description_placeholders={"login_url": login_url(self._country)},
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        self._country = entry_data.get(CONF_COUNTRY, DEFAULT_COUNTRY)
        return await self.async_step_login()

    # ---- step 3: postcode ----

    async def async_step_postcode(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None and self._api is not None:
            self._postcode = user_input[CONF_POSTCODE].replace(" ", "").upper()
            try:
                stores = await self._api.search_stores(self._postcode, int(user_input[CONF_STORE_COUNT]))
            except AHConnectionError:
                errors["base"] = "cannot_connect"
            except AHError:
                errors["base"] = "unknown"
            else:
                if not stores:
                    errors["base"] = "no_stores"
                else:
                    self._found = {s["id"]: s for s in stores}
                    return await self.async_step_stores()
        return self.async_show_form(
            step_id="postcode",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_POSTCODE, default=self._postcode): str,
                    vol.Required(CONF_STORE_COUNT, default=DEFAULT_STORE_COUNT): STORE_COUNT_SELECTOR,
                }
            ),
            errors=errors,
        )

    # ---- step 4: choose stores ----

    async def async_step_stores(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None and self._api is not None:
            chosen = [sid for sid in user_input[CONF_STORES] if sid in self._found]
            if not chosen:
                errors["base"] = "no_selection"
            else:
                return self.async_create_entry(
                    title=f"AH Laatste Kans ({self._postcode})",
                    data={CONF_COUNTRY: self._country, CONF_TOKENS: self._api.tokens},
                    options={
                        CONF_POSTCODE: self._postcode,
                        CONF_STORES: {sid: self._found[sid] for sid in chosen},
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                        CONF_KEYWORDS: "",
                    },
                )
        return self.async_show_form(
            step_id="stores",
            data_schema=vol.Schema(
                {vol.Required(CONF_STORES, default=list(self._found)): _stores_selector(self._found)}
            ),
            errors=errors,
            description_placeholders={"postcode": self._postcode},
        )


class AHOptionsFlow(OptionsFlow):
    """Afterwards: switch stores on/off, search another postcode, interval and watchlist."""

    def __init__(self) -> None:
        self._found: dict[str, dict[str, str]] = {}
        self._postcode = ""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["stores", "search", "settings"])

    def _api(self) -> AHApi:
        entry = self.config_entry
        coordinator = getattr(entry, "runtime_data", None)
        if coordinator is not None:
            return coordinator.api
        return AHApi(async_get_clientsession(self.hass), entry.data[CONF_COUNTRY], entry.data.get(CONF_TOKENS))

    def _save(self, **changes: Any) -> ConfigFlowResult:
        return self.async_create_entry(data={**self.config_entry.options, **changes})

    # ---- switch the current stores on/off ----

    async def async_step_stores(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        current: dict[str, dict[str, str]] = dict(self.config_entry.options.get(CONF_STORES, {}))
        known = {**current, **self._found}
        errors: dict[str, str] = {}
        if user_input is not None:
            chosen = [sid for sid in user_input[CONF_STORES] if sid in known]
            if not chosen:
                errors["base"] = "no_selection"
            else:
                options = {CONF_STORES: {sid: known[sid] for sid in chosen}}
                if self._postcode:
                    options[CONF_POSTCODE] = self._postcode
                return self._save(**options)
        default = [sid for sid in known if sid in current] or list(known)
        return self.async_show_form(
            step_id="stores",
            data_schema=vol.Schema({vol.Required(CONF_STORES, default=default): _stores_selector(known)}),
            errors=errors,
        )

    # ---- find stores near another postcode, then pick ----

    async def async_step_search(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._postcode = user_input[CONF_POSTCODE].replace(" ", "").upper()
            try:
                stores = await self._api().search_stores(self._postcode, int(user_input[CONF_STORE_COUNT]))
            except AHConnectionError:
                errors["base"] = "cannot_connect"
            except AHError:
                errors["base"] = "unknown"
            else:
                if not stores:
                    errors["base"] = "no_stores"
                else:
                    self._found = {s["id"]: s for s in stores}
                    return await self.async_step_stores()
        return self.async_show_form(
            step_id="search",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POSTCODE, default=self.config_entry.options.get(CONF_POSTCODE, "")
                    ): str,
                    vol.Required(CONF_STORE_COUNT, default=DEFAULT_STORE_COUNT): STORE_COUNT_SELECTOR,
                }
            ),
            errors=errors,
        )

    # ---- interval and watchlist ----

    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(
                **{
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    CONF_KEYWORDS: user_input.get(CONF_KEYWORDS, ""),
                }
            )
        options = self.config_entry.options
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL, max=240, step=5, mode=NumberSelectorMode.BOX,
                            unit_of_measurement="min",
                        )
                    ),
                    vol.Optional(CONF_KEYWORDS, default=options.get(CONF_KEYWORDS, "")): TextSelector(
                        TextSelectorConfig(multiline=True)
                    ),
                }
            ),
        )
