/*
 * AH Laatste Kans card for Home Assistant.
 *
 *   type: custom:ah-laatste-kans-card
 *   # all optional:
 *   title: Laatste Kansjes
 *   entities: [sensor.ah_vondellaan_200_utrecht_laatste_kans]   # default: all stores of the integration
 *   min_discount: 0          # only show products with at least this discount (%)
 *   sort: discount           # discount | saving | price | expiry | name
 *   group_by_store: true     # false = one grid over all stores
 *   max_items: 0             # per store (0 = all)
 *   show_images: true
 *   show_controls: true      # search box, min. discount and sort in the card
 */
const CARD_VERSION = "0.1.1";

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
      show_images: true,
      show_controls: true,
      ...(config || {}),
    };
    this._ui = { text: "", min: Number(this._config.min_discount) || 0, sort: SORTS[this._config.sort] ? this._config.sort : "discount" };
    this._built = false;
    this._sig = null;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._built) this._build();
    const sig = this._entities()
      .map((id) => (hass.states[id] ? hass.states[id].last_updated : "x"))
      .join("|");
    if (sig !== this._sig) {
      this._sig = sig;
      this._renderList();
    }
  }

  getCardSize() {
    return 8;
  }

  static getStubConfig() {
    return {};
  }

  _entities() {
    if (!this._hass) return [];
    if (Array.isArray(this._config.entities) && this._config.entities.length) return this._config.entities;
    return Object.keys(this._hass.states)
      .filter((id) => {
        const a = this._hass.states[id].attributes || {};
        return id.startsWith("sensor.") && a.integration === "ah_laatste_kans" && Array.isArray(a.items);
      })
      .sort();
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
        .row { display: flex; justify-content: space-between; align-items: center; gap: 4px; font-size: 0.75em; color: var(--secondary-text-color); }
        .urgent { color: var(--error-color, #d32f2f); font-weight: 600; }
        .stock { background: var(--divider-color); border-radius: 999px; padding: 1px 6px; font-weight: 700; color: var(--primary-text-color); }
        .empty { padding: 16px; color: var(--secondary-text-color); text-align: center; }
      </style>
      <ha-card>
        <div class="head"><div class="title">${esc(c.title)}</div><div class="muted" id="count"></div></div>
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

  _itemHtml(i, storeName) {
    const exp = expiryInfo(i.expires);
    const img = this._config.show_images
      ? `<div class="img">${i.image ? `<img loading="lazy" src="${esc(i.image)}" alt="">` : `<span class="ph">🛒</span>`}</div>`
      : "";
    const tag = i.url ? "a" : "div";
    const href = i.url ? ` href="${esc(i.url)}" target="_blank" rel="noreferrer"` : "";
    return `<${tag} class="item"${href} title="${esc(i.title)}${i.unit ? " · " + esc(i.unit) : ""}">
      ${img}
      <span class="sticker${i.discount >= 50 ? " hot" : ""}">-${esc(i.discount)}%</span>
      <div class="t">${esc(i.title)}</div>
      <div class="muted">${esc([i.brand, i.unit].filter(Boolean).join(" · "))}</div>
      <div class="prices">${i.was ? `<span class="was">${euro(i.was)}</span>` : ""}<span class="now">${euro(i.price)}</span></div>
      <div class="row"><span class="${exp.urgent ? "urgent" : ""}">${esc(exp.text)}</span>${i.stock ? `<span class="stock">×${esc(i.stock)}</span>` : ""}</div>
      ${storeName ? `<div class="muted">${esc(storeName)}</div>` : ""}
    </${tag}>`;
  }

  _renderList() {
    if (!this._root || !this._hass) return;
    const list = this._root.getElementById("list");
    const stores = this._entities()
      .map((id) => this._hass.states[id])
      .filter(Boolean);
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
        let items = this._filter(a.items || []);
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
      for (const st of stores) for (const i of st.attributes.items || []) all.push({ ...i, _store: st.attributes.store });
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
