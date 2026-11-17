/*
 * AH Laatste Kans card for Home Assistant.
 *
 *   type: custom:ah-laatste-kans-card
 *   # all optional:
 *   title: Laatste Kansjes
 *   stores: [Vondellaan, Kanaalweg]   # stores by (part of) their name; default: all stores of the integration
 *   entities: [sensor.ah_vondellaan_200_utrecht_laatste_kans]   # or by sensor, as before
 *   store_select: true       # dropdown to pick one store; follows the select entities of every hub
 *                            # (or give one entity_id or a list, e.g. select.ah_laatste_kans_laatste_kans_winkel)
 *   min_discount: 0          # only show products with at least this discount (%)
 *   sort: discount           # discount | saving | price | expiry | name
 *   group_by_store: true     # false = one grid over all stores
 *   max_items: 0             # per store (0 = all)
 *   columns: 0               # products per row, e.g. 1 or 2 (bigger pictures); 0 = as many as fit
 *   tile_width: 200          # minimum width of a product (px): as many per row as fit, on every screen
 *                            # (wins over columns)
 *   image_size: 160          # height of the pictures (px); default 96, or growing with columns
 *   show_images: true
 *   show_controls: true      # search box, min. discount and sort in the card
 *   cart: true               # cart button: adds "Koopjes (40%) product" to the todo list chosen (tap again: removes it)
 *                            # in the integration settings (hidden when no list is chosen)
 *   fonts:                   # text on the product tiles; a number is a size in em, or give an object
 *     article: 1.1           # product name
 *     brand: 14px            # brand and content/weight
 *     price: 0.9             # original (struck-through) price
 *     discount: { size: 1.4, weight: 800, color: "#e00" }   # new price
 *     amount: { size: 1.2, family: monospace }              # number in stock
 */
const CARD_VERSION = "0.1.12";
const ALL_STORES = "Alle winkels";  // first option of the select entity

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const euro = (v) =>
  v === null || v === undefined || v === "" ? "" : new Intl.NumberFormat("nl-NL", { style: "currency", currency: "EUR" }).format(v);

function expiryInfo(iso) {
  if (!iso) return { text: "", urgent: false };
  const d = new Date(iso + "T00:00:00");
  if (isNaN(d)) return { text: "", urgent: false };
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const days = Math.round((d - today) / 86400000);
  if (days < 0) return { text: "Verlopen", urgent: true };
  if (days === 0) return { text: "Vandaag THT", urgent: true };
  if (days === 1) return { text: "Morgen THT", urgent: true };
  return { text: "THT " + d.toLocaleDateString("nl-NL", { weekday: "short", day: "numeric", month: "short" }), urgent: false };
}

const SORTS = {
  discount: { label: "Hoogste korting", fn: (a, b) => b.discount - a.discount || saving(b) - saving(a) },
  saving: { label: "Meeste besparing", fn: (a, b) => saving(b) - saving(a) },
  price: { label: "Laagste prijs", fn: (a, b) => (a.price ?? 999) - (b.price ?? 999) },
  expiry: { label: "Eerst verlopen", fn: (a, b) => String(a.expires || "9999").localeCompare(String(b.expires || "9999")) },
  name: { label: "Naam", fn: (a, b) => String(a.title).localeCompare(String(b.title), "nl") },
};
// Card option `fonts`: which element each key styles.
const FONT_PARTS = { article: ".t", brand: ".brand", price: ".was", discount: ".now", amount: ".stock" };
// Only plain CSS values: no ; { } < > that could break out of the rule.
const cssValue = (v) => String(v).replace(/[;{}<>\\]/g, "").trim();
const cssSize = (v) => (typeof v === "number" || /^\d+(\.\d+)?$/.test(String(v).trim()) ? `${Number(v)}em` : cssValue(v));

function fontCss(fonts) {
  if (!fonts || typeof fonts !== "object") return "";
  let css = "";
  for (const [key, selector] of Object.entries(FONT_PARTS)) {
    let f = fonts[key];
    if (f === undefined || f === null || f === "") continue;
    if (typeof f !== "object") f = { size: f };
    const rules = [];
    if (f.size !== undefined && f.size !== "") rules.push(`font-size: ${cssSize(f.size)}`);
    if (f.weight !== undefined && f.weight !== "") rules.push(`font-weight: ${cssValue(f.weight)}`);
    if (f.family) rules.push(`font-family: ${cssValue(f.family)}`);
    if (f.style) rules.push(`font-style: ${cssValue(f.style)}`);
    if (f.color) rules.push(`color: ${cssValue(f.color)}`);
    if (rules.length) css += `.item ${selector} { ${rules.join("; ")}; }\n`;
  }
  return css;
}

// Card option `columns`: a fixed number of products per row; the pictures grow with the tiles.
function columnsCss(columns) {
  const n = Math.floor(Number(columns));
  if (!(n >= 1)) return "";
  return `.grid { grid-template-columns: repeat(${Math.min(n, 12)}, minmax(0, 1fr)); }
        .img { height: auto; aspect-ratio: 1 / 1; max-height: 360px; }
        .img img { width: 100%; height: 100%; }`;
}

// Card options `tile_width` and `image_size`: a number is px, or any CSS size.
const pxSize = (v) => (typeof v === "number" || /^\d+(\.\d+)?$/.test(String(v).trim()) ? `${Number(v)}px` : cssValue(v));

function layoutCss(c) {
  let css = "";
  if (c.tile_width) css += `.grid { grid-template-columns: repeat(auto-fill, minmax(min(${pxSize(c.tile_width)}, 100%), 1fr)); }\n`;
  if (c.image_size) css += `.img { height: ${pxSize(c.image_size)}; aspect-ratio: auto; max-height: none; }\n`;
  return css;
}

function saving(i) {
  return Math.max(0, (i.was || 0) - (i.price || 0));
}

class AHLaatsteKansCard extends HTMLElement {
  setConfig(config) {
    this._config = {
      title: "Laatste Kansjes",
      min_discount: 0,
      sort: "discount",
      group_by_store: true,
      max_items: 0,
      columns: 0,
      show_images: true,
      show_controls: true,
      cart: true,
      ...(config || {}),
    };
    this._ui = { text: "", min: Number(this._config.min_discount) || 0, sort: SORTS[this._config.sort] ? this._config.sort : "discount" };
    this._built = false;
    this._sig = null;
    this._cart = [];          // products behind the cart buttons, by index
    this._onList = new Map(); // todo entity -> names of open items on that list (button is ticked)
    this._listsSig = null;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._built) this._build();
    const sig = [...this._entities(), ...this._selectEntities()]
      .map((id) => (hass.states[id] ? hass.states[id].last_updated : "x"))
      .join("|");
    if (sig !== this._sig) {
      this._sig = sig;
      this._renderList();
    }
    // The todo lists themselves: their state (open items) changes when something is added, ticked off or removed,
    // also from another device or the todo panel.
    const lists = this._todoLists();
    const listsSig = lists.map((id) => `${id}:${hass.states[id]?.last_updated}`).join("|");
    if (listsSig !== this._listsSig) {
      this._listsSig = listsSig;
      this._loadLists(lists);
    }
  }

  _todoLists() {
    if (!this._config.cart || !this._hass) return [];
    const ids = this._entities().map((id) => this._hass.states[id]?.attributes.todo_list).filter((id) => id && this._hass.states[id]);
    return [...new Set(ids)];
  }

  async _loadLists(lists) {
    const run = (this._listsRun = (this._listsRun || 0) + 1);
    const map = new Map();
    await Promise.all(
      lists.map(async (id) => {
        try {
          const res = await this._hass.callWS({ type: "todo/item/list", entity_id: id });
          map.set(id, new Set((res.items || []).filter((t) => t.status !== "completed").map((t) => t.summary)));
        } catch (err) {
          map.set(id, this._onList.get(id) || new Set());
        }
      })
    );
    if (run !== this._listsRun) return;  // a newer load is under way
    this._onList = map;
    this._renderList();
  }

  getCardSize() {
    return 8;
  }

  static getStubConfig() {
    return {};
  }

  // All store sensors this card may show: `entities`, or every store of the integration, narrowed by `stores`.
  _entities() {
    if (!this._hass) return [];
    let ids;
    if (Array.isArray(this._config.entities) && this._config.entities.length) {
      ids = this._config.entities;
    } else {
      ids = Object.keys(this._hass.states)
        .filter((id) => {
          const a = this._hass.states[id].attributes || {};
          return id.startsWith("sensor.") && a.integration === "ah_laatste_kans" && Array.isArray(a.items);
        })
        .sort();
    }
    const names = [].concat(this._config.stores || []).map((n) => String(n).trim().toLowerCase()).filter(Boolean);
    if (!names.length) return ids;
    return ids.filter((id) => {
      const a = (this._hass.states[id] || {}).attributes || {};
      const label = String(a.store || a.friendly_name || id).toLowerCase();
      return names.some((n) => label.includes(n));
    });
  }

  // The select entities that pick one store: one per hub (AH account / postcode) of the integration.
  _selectEntities() {
    const opt = this._config.store_select;
    if (!opt || !this._hass) return [];
    if (typeof opt === "string" || Array.isArray(opt)) return [].concat(opt).filter((id) => this._hass.states[id]);
    const reg = this._hass.entities || {};
    return Object.keys(this._hass.states)
      .filter((id) => id.startsWith("select.") && reg[id]?.platform === "ah_laatste_kans")
      .sort();
  }

  // The chosen store over all hubs: the first select that is not on 'Alle winkels'.
  _choice() {
    for (const id of this._selectEntities()) {
      const state = this._hass.states[id].state;
      if (state && state !== ALL_STORES && (this._hass.states[id].attributes.options || []).includes(state)) return state;
    }
    return ALL_STORES;
  }

  // Pick a store in the select of its own hub, and put the other hubs on 'Alle winkels'.
  _choose(option) {
    for (const id of this._selectEntities()) {
      const st = this._hass.states[id];
      const target = option !== ALL_STORES && (st.attributes.options || []).includes(option) ? option : ALL_STORES;
      if (st.state !== target) this._hass.callService("select", "select_option", { entity_id: id, option: target });
    }
  }

  // The stores to draw right now: the chosen one, or all of them.
  _shownStores() {
    const stores = this._entities().map((id) => this._hass.states[id]).filter(Boolean);
    const choice = this._choice();
    const chosen = stores.filter((st) => st.attributes.store === choice);
    // 'Alle winkels', or a store this card does not show: show all of this card's stores.
    return chosen.length ? chosen : stores;
  }

  _renderStorePicker() {
    const picker = this._root.getElementById("store");
    if (!picker) return;
    const selects = this._selectEntities();
    picker.hidden = !selects.length;
    if (!selects.length) return;
    // The stores of every hub, but only those this card may show.
    const allowed = new Set(this._entities().map((id) => this._hass.states[id]?.attributes.store));
    const options = [ALL_STORES];
    for (const id of selects) {
      for (const o of this._hass.states[id].attributes.options || []) {
        if (o !== ALL_STORES && allowed.has(o) && !options.includes(o)) options.push(o);
      }
    }
    const html = options.map((o) => `<option value="${esc(o)}">${esc(o)}</option>`).join("");
    if (picker.innerHTML !== html) picker.innerHTML = html;
    // A store this card does not show counts as 'Alle winkels' (see _shownStores).
    const choice = this._choice();
    picker.value = options.includes(choice) ? choice : ALL_STORES;
  }

  _build() {
    this._built = true;
    const root = this.attachShadow ? this.shadowRoot || this.attachShadow({ mode: "open" }) : this;
    const c = this._config;
    root.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { overflow: hidden; }
        .head { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 12px 16px 4px; }
        .title { font-size: 1.25em; font-weight: 600; flex: 1 1 auto; }
        .picker {
          font: inherit; color: var(--primary-text-color); background: var(--card-background-color);
          border: 1px solid var(--divider-color); border-radius: 8px; padding: 6px 8px; max-width: 100%;
        }
        .controls { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; padding: 0 16px 8px; }
        .controls input, .controls select {
          font: inherit; color: var(--primary-text-color); background: var(--card-background-color);
          border: 1px solid var(--divider-color); border-radius: 8px; padding: 6px 8px;
        }
        .controls input { flex: 1 1 140px; min-width: 120px; }
        .store { padding: 4px 16px 12px; }
        .store-h { display: flex; align-items: baseline; gap: 8px; margin: 8px 0; }
        .store-h b { font-size: 1.05em; }
        .muted { color: var(--secondary-text-color); font-size: 0.85em; }
        .warn { color: var(--warning-color, #f4b400); font-size: 0.85em; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; }
        .item {
          position: relative; display: flex; flex-direction: column; gap: 4px; padding: 8px;
          border-radius: 12px; border: 1px solid var(--divider-color); background: var(--secondary-background-color);
          color: inherit; text-decoration: none; min-width: 0;
        }
        .img { height: 96px; border-radius: 8px; background: #fff; display: flex; align-items: center; justify-content: center; overflow: hidden; }
        .img img { max-width: 100%; max-height: 100%; object-fit: contain; }
        .img .ph { font-size: 32px; opacity: 0.35; }
        .sticker {
          position: absolute; top: 6px; right: 6px; transform: rotate(-6deg); color: #fff; font-weight: 800; font-size: 0.85em;
          padding: 3px 7px; border-radius: 999px; background: #f08a24; box-shadow: 0 1px 2px rgba(0,0,0,.3);
        }
        .sticker.hot { background: #d32f2f; }
        .t { font-weight: 600; font-size: 0.9em; line-height: 1.2; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; min-height: 2.4em; }
        .prices { display: flex; align-items: baseline; gap: 6px; }
        .was { text-decoration: line-through; color: var(--secondary-text-color); font-size: 0.8em; }
        .now { font-weight: 800; color: #f08a24; font-size: 1.1em; }
        .row { display: flex; justify-content: space-between; align-items: center; gap: 4px; font-size: 0.9em; color: var(--secondary-text-color); }
        .urgent { color: var(--error-color, #d32f2f); font-weight: 600; }
        .cart {
          /* flush in the top-left corner of the picture: same rounding as the picture, so no white corner shows */
          position: absolute; top: 8px; left: 8px; z-index: 1; width: 40px; height: 40px; padding: 0; border: none;
          border-radius: 8px 0 14px 0;
          display: flex; align-items: center; justify-content: center; cursor: pointer;
          background: #0a7fd8; color: #fff;  /* fixed blue + white icon, independent of the theme */
          --mdc-icon-size: 22px;
        }
        .cart.done { background: #2e9d48; }
        .cart[disabled] { cursor: default; opacity: 0.6; }
        .stock { background: var(--divider-color); border-radius: 999px; padding: 1px 6px; font-weight: 700; color: var(--primary-text-color); }
        ${columnsCss(c.tile_width ? 0 : c.columns)}
        ${layoutCss(c)}
        ${fontCss(c.fonts)}
        .empty { padding: 16px; color: var(--secondary-text-color); text-align: center; }
      </style>
      <ha-card>
        <div class="head"><div class="title">${esc(c.title)}</div>${c.store_select ? `<select id="store" class="picker" hidden></select>` : ""}<div class="muted" id="count"></div></div>
        ${
          c.show_controls
            ? `<div class="controls">
                 <input id="q" type="search" placeholder="Zoek product of merk">
                 <select id="min">${[0, 25, 35, 50, 70].map((v) => `<option value="${v}">${v ? "≥ " + v + "%" : "Alle kortingen"}</option>`).join("")}</select>
                 <select id="sort">${Object.entries(SORTS).map(([k, s]) => `<option value="${k}">${s.label}</option>`).join("")}</select>
               </div>`
            : ""
        }
        <div id="list"></div>
      </ha-card>`;
    this._root = root;
    root.getElementById("list").addEventListener("click", (ev) => {
      const btn = ev.target.closest && ev.target.closest(".cart");
      if (!btn) return;
      ev.preventDefault();  // the tile is a link to ah.nl
      ev.stopPropagation();
      this._toggleCart(btn);
    });
    const picker = root.getElementById("store");
    if (picker) {
      picker.addEventListener("change", () => this._choose(picker.value));
    }
    if (c.show_controls) {
      const q = root.getElementById("q");
      const min = root.getElementById("min");
      const sort = root.getElementById("sort");
      if (![...min.options].some((o) => Number(o.value) === this._ui.min)) {
        min.insertAdjacentHTML("beforeend", `<option value="${this._ui.min}">≥ ${this._ui.min}%</option>`);
      }
      min.value = String(this._ui.min);
      sort.value = this._ui.sort;
      q.addEventListener("input", () => { this._ui.text = q.value; this._renderList(); });
      min.addEventListener("change", () => { this._ui.min = Number(min.value); this._renderList(); });
      sort.addEventListener("change", () => { this._ui.sort = sort.value; this._renderList(); });
    }
  }

  _filter(items) {
    const text = this._ui.text.trim().toLowerCase();
    return items
      .filter((i) => (i.discount || 0) >= this._ui.min)
      .filter((i) => !text || `${i.title} ${i.brand}`.toLowerCase().includes(text))
      .sort(SORTS[this._ui.sort].fn);
  }

  _listName(i) {
    return `Koopjes (${i.discount}%) ${i.title}`;
  }

  _isOnList(i, todo) {
    return !!this._onList.get(todo)?.has(this._listName(i));
  }

  _setCartButton(btn, done) {
    btn.classList.toggle("done", done);
    btn.querySelector("ha-icon").setAttribute("icon", done ? "mdi:cart-check" : "mdi:cart-plus");
    btn.title = done ? "Staat op je lijst (tik om weg te halen)" : "Op de boodschappenlijst";
  }

  // First tap: on the todo list. Tap again: off the list.
  async _toggleCart(btn) {
    const entry = this._cart[Number(btn.dataset.i)];
    if (!entry || btn.disabled) return;
    const { item: i, todo } = entry;
    const name = this._listName(i);
    if (!this._onList.has(todo)) this._onList.set(todo, new Set());
    const names = this._onList.get(todo);
    btn.disabled = true;
    if (names.has(name)) {
      try {
        await this._hass.callService("todo", "remove_item", { entity_id: todo, item: name });
        names.delete(name);
        this._setCartButton(btn, false);
        this._toast(`Van de lijst gehaald: ${name}`);
      } catch (err) {
        this._toast(`Weghalen mislukt: ${err.message || err}`);
      }
      btn.disabled = false;
      return;
    }
    const data = { entity_id: todo, item: name };
    // Price, store and date as the item's description, when the list supports that (64 = SET_DESCRIPTION_ON_ITEM).
    const features = this._hass.states[todo]?.attributes.supported_features || 0;
    if (features & 64) {
      const exp = expiryInfo(i.expires).text;
      data.description = [
        [i.brand, i.unit].filter(Boolean).join(" · "),
        `${euro(i.price)}${i.was ? ` (was ${euro(i.was)})` : ""}`,
        i._store_name,
        exp,
      ].filter(Boolean).join("\n");
    }
    try {
      await this._hass.callService("todo", "add_item", data);
      names.add(name);
      this._setCartButton(btn, true);
      this._toast(`Op de lijst: ${name}`);
    } catch (err) {
      this._toast(`Toevoegen mislukt: ${err.message || err}`);
    }
    btn.disabled = false;
  }

  _toast(message) {
    this.dispatchEvent(new CustomEvent("hass-notification", { detail: { message }, bubbles: true, composed: true }));
  }

  _itemHtml(i, storeName) {
    const exp = expiryInfo(i.expires);
    const img = this._config.show_images
      ? `<div class="img">${i.image ? `<img loading="lazy" src="${esc(i.image)}" alt="">` : `<span class="ph">🛒</span>`}</div>`
      : "";
    const tag = i.url ? "a" : "div";
    const href = i.url ? ` href="${esc(i.url)}" target="_blank" rel="noreferrer"` : "";
    return `<${tag} class="item"${href} title="${esc(i.title)}${i.unit ? " · " + esc(i.unit) : ""}">
      ${img}
      ${this._cartHtml(i)}
      <span class="sticker${i.discount >= 50 ? " hot" : ""}">-${esc(i.discount)}%</span>
      <div class="t">${esc(i.title)}</div>
      <div class="muted brand">${esc([i.brand, i.unit].filter(Boolean).join(" · "))}</div>
      <div class="prices">${i.was ? `<span class="was">${euro(i.was)}</span>` : ""}<span class="now">${euro(i.price)}</span></div>
      <div class="row"><span class="${exp.urgent ? "urgent" : ""}">${esc(exp.text)}</span>${i.stock ? `<span class="stock">×${esc(i.stock)}</span>` : ""}</div>
      ${storeName ? `<div class="muted">${esc(storeName)}</div>` : ""}
    </${tag}>`;
  }

  _cartHtml(i) {
    const todo = i._todo;
    if (!this._config.cart || !todo || !this._hass.states[todo]) return "";
    const done = this._isOnList(i, todo);
    this._cart.push({ item: i, todo });
    return `<button class="cart${done ? " done" : ""}" data-i="${this._cart.length - 1}"
      title="${done ? "Staat op je lijst (tik om weg te halen)" : "Op de boodschappenlijst"}"><ha-icon icon="mdi:cart-${done ? "check" : "plus"}"></ha-icon></button>`;
  }

  _renderList() {
    if (!this._root || !this._hass) return;
    this._cart = [];
    const list = this._root.getElementById("list");
    this._renderStorePicker();
    const stores = this._shownStores();
    if (!stores.length) {
      list.innerHTML = `<div class="empty">Geen AH Laatste Kans-winkels gevonden. Voeg de integratie toe of kies winkels.</div>`;
      this._root.getElementById("count").textContent = "";
      return;
    }
    const max = Number(this._config.max_items) || 0;
    let total = 0;
    let html = "";
    if (this._config.group_by_store) {
      for (const st of stores) {
        const a = st.attributes;
        const extra = { _store: a.store, _store_name: a.store, _store_id: a.store_id, _todo: a.todo_list };
        let items = this._filter((a.items || []).map((i) => ({ ...i, ...extra })));
        total += items.length;
        if (max) items = items.slice(0, max);
        html += `<div class="store">
          <div class="store-h"><b>${esc(a.store || a.friendly_name)}</b><span class="muted">${items.length} producten</span>
          ${a.error ? `<span class="warn" title="${esc(a.error)}">⚠︎ verouderd</span>` : ""}</div>
          ${items.length ? `<div class="grid">${items.map((i) => this._itemHtml(i)).join("")}</div>` : `<div class="muted">Niets dat past bij je filter.</div>`}
        </div>`;
      }
    } else {
      let all = [];
      for (const st of stores) for (const i of st.attributes.items || []) all.push({ ...i, _store: st.attributes.store, _store_name: st.attributes.store, _store_id: st.attributes.store_id, _todo: st.attributes.todo_list });
      all = this._filter(all);
      total = all.length;
      if (max) all = all.slice(0, max);
      html = all.length
        ? `<div class="store"><div class="grid">${all.map((i) => this._itemHtml(i, i._store)).join("")}</div></div>`
        : `<div class="empty">Niets dat past bij je filter.</div>`;
    }
    list.innerHTML = html;
    this._root.getElementById("count").textContent = `${total} kansjes · ${stores.length} winkel${stores.length === 1 ? "" : "s"}`;
  }
}

if (!customElements.get("ah-laatste-kans-card")) {
  customElements.define("ah-laatste-kans-card", AHLaatsteKansCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "ah-laatste-kans-card",
    name: "AH Laatste Kans",
    description: "Laatste Kans-stickers per Albert Heijn-winkel",
    preview: true,
  });
  console.info(`%c AH-LAATSTE-KANS-CARD %c ${CARD_VERSION} `, "color:#fff;background:#00a0e3;font-weight:700", "color:#00a0e3");
}
