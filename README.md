# 🏠 AH Laatste Kans for Home Assistant

A custom integration that brings the **Albert Heijn "Laatste Kans"** (last chance) bargains of your local stores
into Home Assistant, with its own dashboard card.

Albert Heijn puts a "Laatste Kans" sticker on products that are close to their best-before date and sells them
with 25–90% off. This integration shows, per store, which products have such a sticker right now: name, brand,
old and new price, discount, how many are left and the best-before date. You can filter and group them on a
dashboard, put them on your shopping list with one tap, and get a notification when something on your
watchlist turns up.

> ⚠️ **Unofficial.** This integration uses the non-public API of the Albert Heijn app. It is not made or supported
> by Albert Heijn, and AH can change or block that API at any moment.

![Card](docs/card-preview.png)

## Requirements

- Home Assistant 2025.1 or newer.
- An Albert Heijn account (the free account you use in the AH app or on ah.nl).
- Stores in the **Netherlands** or **Belgium**.

## Features

- One sensor per store with all its Laatste Kans products.
- A total sensor with the best deals over all your stores.
- A **watchlist**: keywords such as `salmon, Ben & Jerry, cheese`, with an event (and so a push notification)
  when a match appears.
- A **dashboard card** with search, grouping per product group, discount and price filters, sorting and a store
  picker. It works on a phone, a tablet and a wide screen.
- A **cart button** on every product that puts it on any Home Assistant to-do list as
  `Koopjes (40%) Product name`, and takes it off again with a second tap.
- Several hubs (for example stores near home and near work) in one card.

## Installation

### With HACS / the Home Assistant Marketplace (recommended)

1. Open HACS (in Home Assistant 2026.11 and newer: the **Marketplace**).
2. Add a **custom repository**:
   `https://github.com/poudenes/AH-Laatste-kansjes-Home-Assistant-Integration`, type **Integration**.
3. Search for **AH Laatste Kans** and install it.
4. Restart Home Assistant if you are asked to.
5. Go to **Settings › Devices & services › Add integration › AH Laatste Kans**.

New versions show up as updates in HACS / the Marketplace.

### Manual

1. Copy the folder `custom_components/ah_laatste_kans` to `/config/custom_components/` on your Home Assistant,
   for example with the Samba share or SSH add-on.
2. Restart Home Assistant.
3. Go to **Settings › Devices & services › Add integration › AH Laatste Kans**.

## Setup

1. **Country:** the Netherlands or Belgium.
2. **Log in to Albert Heijn** (see below).
3. **Postcode:** your postcode and how many nearby stores to look for.
4. **Stores:** tick the stores you want. Each store gets its own device and sensor.

### Logging in (Home Assistant never sees your password)

AH's login page uses reCAPTCHA and a 6-digit verification code, so Home Assistant does **not** ask for your
password. You log in on AH's own page. At the end that page sends your browser to a link meant for the AH app:
`appie://login-exit?code=…`. You paste that link (or only the code) into Home Assistant, which trades it for a
login token.

**In a desktop browser (Chrome, Edge, Firefox):**
1. In the login step, click the link to AH's login page. Before you log in, open the developer tools
   (**F12**, or **⌥⌘I** on a Mac) and go to the **Console** tab.
2. Log in with your e-mail, password and the 6-digit code.
3. The browser cannot open the `appie://` link, so it shows an error in the console with
   `appie://login-exit?code=…`. Copy that whole link.
4. Paste it into Home Assistant and submit **right away**: the code expires within a few minutes.

AH's verification step sometimes refuses a regular browser, because the login is meant for the AH app. If that
happens, try again a bit later or in another browser.

After that, Home Assistant refreshes its token by itself. You only log in again when AH really ends the session;
Home Assistant then asks for it with a notification. A hiccup at AH (for example maintenance at night) does not
count: Home Assistant only asks you to log in again when AH refuses the login three updates in a row.

### Changing things later

**Settings › Devices & services › AH Laatste Kans › Configure:**
- **Stores:** switch stores on or off. A store you switch off disappears with its device and sensor.
- **Find stores:** search near another postcode; the stores found are added to the list.
- **Settings:** update interval (at least 15 minutes), the watchlist keywords (separated by commas), and the
  **shopping list** for the cart button on the card (any to-do list, for example HA's Shopping List).

Want stores near two addresses with their own totals? Add the integration a second time with the other postcode.

## Entities

The entity IDs depend on the language Home Assistant had when you added the integration. In English:

| Entity | State | Attributes |
|---|---|---|
| `sensor.ah_<street>_<nr>_<city>_laatste_kans` (one per store, each its own device) | number of products | `items` (title, brand, price, old price, discount, stock, best-before date, picture, link, product group), `best_discount`, `categories`, address |
| `sensor.ah_laatste_kans_laatste_kans_total` | total over all stores | `top`: the 10 best deals |
| `sensor.ah_laatste_kans_laatste_kans_watchlist` | number of watchlist matches | `keywords`, `matches` |
| `select.ah_laatste_kans_laatste_kans_store` | the store shown in the card | `options`: *Alle winkels* (all stores) + your stores |

With Home Assistant in Dutch these end in `_totaal`, `_volglijst` and `_winkel`. A second hub gets `_2`, and so on.

**Why one sensor per store and not one per product?** Laatste Kans products change every day. A sensor per
product would keep appearing and disappearing and clutter your entity registry. One sensor per store has a stable
name and keeps the product list in an attribute. That list is often bigger than the 16 KB the recorder wants to
store (60 products ≈ 21 KB), so it is left out of the history. The live state, and so your dashboard, always has
the full list. The state (the number of products) is recorded, so you can still make graphs.

### Event

The integration fires an event `ah_laatste_kans_new_bargain` for every product that was not there at the previous
update. Products that match your watchlist also fire once when they were already there, for example right after
you saved the watchlist. After that they do not fire again, not even after a restart.

| Field | Meaning |
|---|---|
| `title`, `brand` | product |
| `price`, `was`, `discount` | new price, old price, discount in % |
| `stock`, `expires` | how many are left, best-before date |
| `store`, `store_id` | the store |
| `image`, `url` | picture and link to the product on ah.nl / ah.be |
| `watched`, `matched_keywords` | `true` and the keywords when it matches your watchlist |

## The card

The card is loaded automatically. Add it via **Dashboard › Add card › AH Laatste Kans**, or in YAML:

```yaml
type: custom:ah-laatste-kans-card
```

That is all you need: the card then shows every store of the integration. Everything below is optional.

The card's own texts are in Dutch (for example *Groeperen* = group, *Alle winkels* = all stores,
*Laagste prijs* = lowest price), as Albert Heijn is a Dutch and Belgian supermarket.

### Filter bar

At the top of the card:
- **Search** for a product or brand.
- **Groeperen** (group): show the products per product group, as in the AH app.
- **Korting** (discount): *Vanaf* = this discount or more, *Precies* = exactly this discount.
- **Prijs (€)** (price): only products with a new price from … to … (both included).
- **Sorteren** (sort): highest discount, biggest saving, lowest price, expires first, or name.

The card remembers these choices after a refresh, per card and per device. Set `remember: false` to always start
with the settings from your YAML.

### All options

```yaml
type: custom:ah-laatste-kans-card
title: Laatste Kansjes
stores:                   # stores by (part of) their name; default: all stores of the integration
  - Vondellaan
  - Kanaalweg
# entities:               # or pick them by sensor
#   - sensor.ah_vondellaan_200_utrecht_laatste_kans
store_select: true        # menu to show one store at a time (see below)
min_discount: 35          # start with: only 35% off or more
# exact_discount: 40      # or: only exactly 40% off
# min_price: 0.50         # only a new price from € 0.50 ...
# max_price: 1.40         # ... up to and including € 1.40
sort: discount            # discount | saving | price | expiry | name
group_by_category: false  # start with grouping per product group on
group_by_store: true      # false = one grid over all stores
max_items: 12             # per store, 0 = all; ignored when grouping
tile_width: 200           # minimum width of a product (px): as many per row as fit, on every screen
image_size: 160           # height of the pictures (px), default 96
# columns: 2              # or a fixed number per row (pictures grow with it); tile_width wins
show_images: true
show_controls: true       # the filter bar
remember: true            # keep the choices in the filter bar after a refresh
cart: true                # cart button on every product (see below)
fonts:                    # text size and style per part (see below)
  article: 1.1
color:                    # text colour per part (see below)
  discount: "#e00000"
```

Click a product to open it on ah.nl / ah.be.

### Phone, tablet and wide screen

With `tile_width` the card adapts to the space it has: on a phone 1 or 2 products per row, on a tablet 3 or 4,
and in a wide *panel* view 6 or more. With `image_size` the pictures have the same height everywhere, so text and
picture keep the same proportions. `columns` gives a fixed number per row, with pictures that grow with the
width. If you set both, `tile_width` wins.

### Fonts per part

With `fonts` you change the text on the product tiles and the group headers. A number is a size in `em`
(1 = normal), but `14px` works too. For more, give an object with `size`, `weight`, `family`, `style` and/or
`color`.

| Key | What | Default |
|---|---|---|
| `article` | product name | `0.9`, bold |
| `brand` | brand and content/weight | `0.85` |
| `price` | old (struck-through) price | `0.8` |
| `discount` | new price | `1.1`, extra bold, orange |
| `amount` | number left (`×3`) | `1` (relative to the best-before line) |
| `group` | product group header (when grouping) | `0.95`, bold |

```yaml
fonts:
  article: 1.1
  brand: 14px
  price: { size: 0.9, color: grey }
  discount: { size: 1.4, weight: 900 }
  amount: { size: 1.2, family: monospace }
  group: 15px
```

### Colour per part

With `color` you give each part (the same keys as `fonts`) its own text colour. You can write a colour in
several ways:

```yaml
color:
  article: default      # default = the normal colour
  brand: yellow         # a colour name, "#ffcc00" or rgb(...)
  price: 255,255,0      # red, green, blue (0-255); a 4th number is the opacity (0-1)
  discount: 0.70,0.30   # x,y as with lights in Home Assistant (xy_color)
  amount: green
  group: "#00a0e2"
```

Lists work too: `price: [255, 255, 0]`. Put a `#` colour between quotes, otherwise YAML reads it as a comment.
`color` wins over a `color` inside `fonts`.

### One card, pick a store

With `store_select: true` the card gets a **Winkel** (store) menu at the top: *Alle winkels* (all stores) or one
store. The menu belongs to the entity `select.ah_laatste_kans_laatste_kans_store`, which the integration creates
itself. When you switch a store on or off in the options, the menu follows. Your choice is kept, also after a
restart.

Because it is a normal entity, you can also pick the store from another card, an automation or a script
(`select.select_option`). Note that the choice is shared: it applies to everyone and to every dashboard with
`store_select`.

With more than one hub (for example a second postcode), every hub has its own select entity (`…_store`,
`…_store_2`). The card merges them into one menu with the stores of all hubs. When you pick a store, the select of
the other hubs goes to *Alle winkels*. To show only one hub in the menu, give its entity: `store_select: select.…`
(or a list).

### Cart button: on your shopping list

In **Configure › Settings**, choose a **shopping list** (any to-do list). Every product in the card then gets a
cart button in the top-left corner of its picture. Tap it and the product goes on that list as

```
Koopjes (40%) AH Zalmfilet
```

so in the store you have your list at hand and know which discount belongs to it. If the list can store a
description (Local To-do can), it also gets the brand, price, store and best-before date. The button turns green
with a tick once the product is on the list; tap it again to take it off.

The card looks at the list itself: when the product is on it (and not ticked off), the button is green, also after
a refresh or on another device. Tick it off or remove it in the list and the button turns blue again. No list
chosen, or `cart: false`? Then there is no cart button. With several hubs, every product uses the list of its
own hub.

## Notification for a watchlist match

```yaml
alias: Laatste Kans watchlist match
triggers:
  - trigger: event
    event_type: ah_laatste_kans_new_bargain
    event_data:
      watched: true
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "🛒 {{ trigger.event.data.title }} -{{ trigger.event.data.discount }}%"
      message: >-
        € {{ trigger.event.data.was }} → € {{ trigger.event.data.price }}
        at {{ trigger.event.data.store }} (×{{ trigger.event.data.stock }})
      data:
        image: "{{ trigger.event.data.image }}"
        url: "{{ trigger.event.data.url }}"
```

Without the `watched: true` filter you get a notification for **every** new product. Fun for one store, but a lot.
😄

## Troubleshooting

- **The card shows an old version after an update:** refresh the dashboard (in the app: pull down, or clear the
  frontend cache in the companion app settings).
- **"AH refused the code":** the code expired or was already used. Log in again and paste the new code right away.
- **Fewer products than in the AH app:** check `max_items`, `min_discount` and the price filter in the card. The
  integration also updates every 30 minutes by default, while the app is live.
- **Debug logging:**
  ```yaml
  logger:
    logs:
      custom_components.ah_laatste_kans: debug
  ```

## Development

```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements_test.txt
pytest            # config flow, sensors, options, events, reauth, HTTP layer
```

On every push GitHub Actions checks the integration with **hassfest** (the official Home Assistant checks), the
**HACS validation** and the tests.

### Releasing a new version

1. Raise `version` in `custom_components/ah_laatste_kans/manifest.json`, `VERSION` in `const.py` and
   `CARD_VERSION` in `frontend/ah-laatste-kans-card.js`.
2. Create a GitHub release with tag `v<version>`. HACS / the Marketplace picks it up by itself.

Issues and pull requests are welcome: [issue tracker](https://github.com/poudenes/AH-Laatste-kansjes-Home-Assistant-Integration/issues).

## Credits

How the AH endpoints work is based on [gwillem/appie-go](https://github.com/gwillem/appie-go). No code was copied.

Albert Heijn, AH and Laatste Kans are trademarks of Albert Heijn B.V. This project is not affiliated with or
endorsed by Albert Heijn.
