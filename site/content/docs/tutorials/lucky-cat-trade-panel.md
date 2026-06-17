---
title: Build a Live Trade Panel in 20 Minutes
description: A from-scratch build-along — markets grid Page, then ValidationError vs FormAction on POST /trade/order
draft: false
weight: 12
lang: en
type: doc
tags: [tutorial, chirp-ui, lucky-cat, page, validation-error, form-action, oob, htmx]
keywords: [lucky cat, trade panel, page, validationerror, formaction, oob, build-along, markets grid]
category: tutorial
---

## What you'll build

One vertical slice of the [[docs/examples/lucky-cat|Lucky Cat]] trading-floor demo. By the end you have two routes that show how Chirp's return type expresses intent — the type you return decides what the browser sees:

1. **`GET /`** — a markets grid rendered as a full [[docs/about/core-concepts/return-values|`Page`]] inside the [[docs/build-apps/ui-extensions/chirp-ui|ChirpUI app shell]]. A `Page` paints the full app shell (topbar, rail, and your content block).
2. **`POST /trade/order`** — the return-type pair that makes the trade panel feel live:
   - invalid input → a [[docs/build-apps/forms-data/forms-validation|`ValidationError`]], which re-renders one block at **422** with field errors preserved;
   - a clean fill → a `FormAction`, which swaps fragments for htmx and **303**-redirects for plain POST, plus **multi-target [[docs/quality/contracts-debugging/oob-registry|OOB fragments]]** (positions table, open-order badge, toast).

You will *not* wire SSE, Suspense, or auth in this walkthrough — those layers ship in the full example. The patterns here are the same ones Lucky Cat uses in production; this tutorial strips them down so you can build the slice in about twenty minutes.

**Prerequisites:** Python 3.14+, `pip install "bengal-chirp[ui]"`, basic htmx familiarity.

**Reference implementation:** [`examples/chirpui/lucky_cat/`](https://github.com/lbliii/chirp/tree/main/examples/chirpui/lucky_cat) — compare your work against `pages/page.py`, `pages/trade/page.html`, and the `/trade/order` handler in `app.py`.

::::{steps}

:::{step} Scaffold (~2 min)

```bash
chirp new trade-slice --shell
cd trade-slice
```

The `--shell` flag scaffolds an `app.py` with [[docs/build-apps/ui-extensions/boosted-navigation|boosted navigation]] (`#main` swaps), CSRF, and the secure middleware stack (Session → CSRF → SecurityHeaders) — the same foundation Lucky Cat builds on. It also scaffolds a layout that extends the [[docs/build-apps/ui-extensions/chirp-ui|ChirpUI app shell]].

Wire the ChirpUI runtime so the app serves `chirpui.css`, the ChirpUI filters, and the ChirpUI contract checks. Add this to the scaffolded `app.py`, after `app = App(config=config)`:

```python
from chirp import use_chirp_ui

use_chirp_ui(app)
```

The scaffold does not call `use_chirp_ui(app)` for you. Skip it and an app whose layout extends a ChirpUI layout serves unstyled chrome and trips the `chirpui_runtime` contract check.

Add a tiny simulated market list (Lucky Cat's real feed lives in `feed.py`; we inline the shape for speed):

```python
# markets.py — DOMAIN (teaching stub; Lucky Cat uses SimFeed)
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Market:
    symbol: str
    display_name: str
    quote: str = "$MEOW"

MARKETS = (
    Market("BTC-$MEOW", "Bitcoin"),
    Market("ETH-$MEOW", "Ethereum"),
    Market("SOL-$MEOW", "Solana"),
)
```

Register it once so every mounted page can depend on `markets_list` from `_context.py`. A `_context.py` provider must export a function named **`context`** that returns a dict; Chirp merges that dict into the cascade context. A function with any other name is ignored.

```python
# pages/_context.py
import markets

def context() -> dict:
    return {"markets_list": markets.MARKETS}
```
:::{/step}

:::{step} Markets grid — `GET /` as `Page` (~6 min)

[[docs/build-apps/pages-navigation/filesystem-routing|Filesystem routing]] maps `pages/page.py` → `GET /`. Return a **`Page`** when the response should paint the full app shell (topbar + rail + your content block).

**Handler** (`pages/page.py`):

```python
from chirp import Page

def get(markets_list) -> Page:
    return Page(
        "home/page.html",
        "page_content",
        page_block_name="page_root",
        markets=markets_list,
    )
```

The three positional args to `Page` are the teaching contract:

| Argument | Role |
|----------|------|
| `"home/page.html"` | Template path under `pages/` |
| `"page_content"` | Block swapped into the shell on boosted navigation |
| `page_block_name="page_root"` | Outer wrapper id (`#page-root`) the shell selects |

**Template** (`pages/home/page.html`):

```html
{% block page_root %}
<div id="page-root">
{% block page_content %}
<div class="page">
  <header>
    <h1>Markets</h1>
    <p class="muted">Pick a market, then head to Trade to place an order.</p>
  </header>

  <div id="markets-grid" class="markets-grid">
    {% for m in markets %}
    <a class="market-card" href="/markets/{{ m.symbol }}">
      <span class="market-card__sym">{{ m.symbol }}</span>
      <span class="market-card__name">{{ m.display_name }}</span>
    </a>
    {% end %}
  </div>

  <p><a href="/trade">Open trade panel →</a></p>
</div>
{% end %}
</div>
{% end %}
```

Mount pages last in `app.py`:

```python
app.mount_pages("pages")
```

Run `python app.py` and open `http://127.0.0.1:8000/`. You should see a grid inside the ChirpUI shell. Boosted links swap only `#main`; the rail re-renders server-side from the current path.

:::{note}
In the shipping Lucky Cat example, `GET /` is an **alias** for the curated Markets Home lobby (`pages/page.py` and `pages/markets/page.py` share `lobby.lobby_context` so the two routes never drift). The **`Page` return type and `#markets-grid` id** are the same idea — a bounded card grid as your landing surface. See [`pages/_components/market.html`](https://github.com/lbliii/chirp/blob/main/examples/chirpui/lucky_cat/pages/_components/market.html) for the production `market_grid` macro.
:::
:::{/step}

:::{step} Trade room — the order form (~4 min)

Add `pages/trade/page.py` → `GET /trade`. Still a **`Page`**, but now the template owns the form markup the mutation route will re-render.

**Handler** (`pages/trade/page.py`):

```python
import trade_store
from chirp import Page

def get(markets_list) -> Page:
    return Page(
        "trade/page.html",
        "page_content",
        page_block_name="page_root",
        markets=markets_list,
        positions=trade_store.positions(),
        open_order_count=trade_store.open_order_count(),
    )
```

Extract the form body into a **`{% def %}`** so the full-page render and the 422 re-render emit identical markup — Lucky Cat's `order_form_body` in `pages/trade/page.html` is the canonical pattern:

```html
{% def order_form_body(markets=(), form=none, errors=none) %}
{% set f = form ?? {} %}
{% set errs = errors ?? {} %}
<form id="order-form"
      hx-post="{{ url_for('trade.order') }}"
      hx-swap="none"
      hx-disabled-elt="find button">
  {{ csrf_field() }}
  <label>Market
    <select name="symbol">
      {% for m in markets %}
      <option value="{{ m.symbol }}"
        {{ "selected" if m.symbol == (f?["symbol"] ?? "") else "" }}>
        {{ m.symbol }}
      </option>
      {% end %}
    </select>
  </label>
  <label>Size
    <input type="number" name="size" step="any"
           value="{{ f?['size'] ?? '' }}">
    {% if errs?["size"] %}
    <ul class="field-errors">{% for msg in errs["size"] %}<li>{{ msg }}</li>{% end %}</ul>
    {% end %}
  </label>
  <button type="submit">Place order</button>
</form>
{% end %}

{% block page_content %}
<section aria-label="Place order">
  {% block order_form %}
  {{ order_form_body(markets=markets, form=form ?? none, errors=errors ?? none) }}
  {% end %}
</section>
<section aria-label="Positions">
  <h2>Open orders: <span id="open-order-count">{{ open_order_count ?? 0 }}</span></h2>
  <div id="positions">
    {% if positions %}
    <table>...</table>
    {% else %}
    <p class="muted">No positions yet.</p>
    {% end %}
  </div>
</section>
{% end %}
```

Register the mutation route in **`app.py` before `mount_pages`** (Lucky Cat registers all mutations ahead of the filesystem mount so route names resolve cleanly):

```python
@app.route("/trade/order", methods=["POST"], name="trade.order")
async def place_order(request: Request):
    ...
```
:::{/step}

:::{step} Invalid order → `ValidationError` (422 in place) (~4 min)

When validation fails, return **`ValidationError(template, block, …)`**. Chirp responds with **422** and re-renders *only* the named block — field errors and submitted values preserved, no navigation.

```python
from chirp import FormAction, Fragment, Request, ValidationError

_TRADE_TEMPLATE = "trade/page.html"

@app.route("/trade/order", methods=["POST"], name="trade.order")
async def place_order(request: Request):
    form = await request.form()
    symbol = (form.get("symbol") or "").strip()
    size_raw = (form.get("size") or "").strip()
    values = {"symbol": symbol, "size": size_raw}

    errors, parsed = trade_store.validate_order(symbol, size_raw)
    if errors:
        return ValidationError(
            _TRADE_TEMPLATE,
            "order_form",
            errors=errors,
            form=values,
            markets=markets.MARKETS,
        )

    # success path — next section
```

**Try it:** submit an empty size or an amount larger than your balance. The form stays put; htmx swaps the `order_form` block; the shell chrome does not reload.

The form uses `hx-swap="none"` because **`ValidationError` targets the block directly** — htmx does not need a primary swap target. That matches Lucky Cat's trade form and avoids inheriting the boosted shell's `#main` target.

:::{tip}
The login flow in [`pages/login/page.py`](https://github.com/lbliii/chirp/blob/main/examples/chirpui/lucky_cat/pages/login/page.py) uses the same **`ValidationError` → 422** pattern. If form swaps land in the wrong place inside a boosted shell, add an explicit `hx-select="#order-form"` on the form — see [[docs/build-apps/ui-extensions/app-shell|App Shells]].
:::
:::{/step}

:::{step} Clean fill → `FormAction` + multi-target OOB (~4 min)

On success, return **`FormAction(redirect, primary_fragment, *oob_fragments)`**:

- **htmx** — primary fragment swaps the form; OOB fragments (`hx-swap-oob` baked in the template) update distant targets in one response.
- **plain POST (no JS)** — **303** redirect to `redirect` (the no-JS floor).

```python
def _toast(message: str) -> Fragment:
    return Fragment("_components/toast_oob.html", "toast", message=message)

@app.route("/trade/order", methods=["POST"], name="trade.order")
async def place_order(request: Request):
    ...
    order = trade_store.try_place_order(symbol, parsed["size"], parsed["fill_price"])
    if order is None:
        return ValidationError(...)  # concurrent balance race — same 422 path

    return FormAction(
        "/trade",
        # Primary swap — reset the form (empty values, no errors).
        Fragment(_TRADE_TEMPLATE, "order_form", markets=markets.MARKETS, form={}, errors=None),
        # OOB twins — each bakes its own id + hx-swap-oob in the template.
        Fragment(_TRADE_TEMPLATE, "positions_oob", positions=trade_store.positions()),
        Fragment(_TRADE_TEMPLATE, "open_order_count_oob",
                 open_order_count=trade_store.open_order_count()),
        _toast(f"Filled buy {order.size:g} {order.symbol}."),
    )
```

Add the OOB fragment blocks at the bottom of `trade/page.html` (Lucky Cat keeps them beside the full-page twins):

```html
{% fragment positions_oob %}
<div id="positions" hx-swap-oob="innerHTML">
  {# same table body as the full-page #positions block #}
</div>
{% endfragment %}

{% fragment open_order_count_oob %}
<span id="open-order-count" hx-swap-oob="innerHTML">{{ open_order_count ?? 0 }}</span>
{% endfragment %}
```

**Try it:** place a small market buy. The form clears, the positions table updates, the open-order badge changes, and a toast appears — one round trip, zero client-side state.

:::{dropdown} Advanced: pushing a live balance signal on fill

A fill in the full example also pushes the new $MEOW balance through a [[docs/build-apps/streaming-updates/signals|live signal]] so the topbar updates over `/_chirp/live` instead of an OOB twin. That is the declare-once / bind-many signal pattern — out of scope for this slice.

The framework primitive is `app.emit(name, value, *, audience_key="")`. Lucky Cat wraps it in a small local `emit_signal(...)` helper (in `examples/chirpui/lucky_cat/app.py`, not importable from `chirp`) that resolves the per-session audience key for you:

```python
# Lucky Cat fan-out: a fill emits the new balance to the visitor's session.
app.emit("balance", new_balance, audience_key=session_key)
```

The OOB set this tutorial reproduces lives in `_fill_fragments()` in that same `app.py`.
:::{/dropdown}
:::{/step}

::::{/steps}

## Return-type cheat sheet

| User action | Return type | HTTP | What the browser sees |
|-------------|-------------|------|------------------------|
| Load `/` or `/trade` | `Page` | 200 | Full shell + content block |
| Bad order fields | `ValidationError` | 422 | `order_form` block re-rendered in place |
| Successful fill | `FormAction` | 200 + OOB / 303 | Form reset + positions + badge + toast |

Read [[docs/about/core-concepts/return-values|Return Values]] for the full decision tree.

## Checklist

Before you call the slice done:

| Check | |
|-------|---|
| `GET /` returns `Page(..., page_block_name="page_root")` | ☐ |
| Grid lives in `#markets-grid` | ☐ |
| Form posts to `url_for('trade.order')` with `csrf_field()` | ☐ |
| Validation failures return `ValidationError(..., "order_form", ...)` | ☐ |
| Success returns `FormAction` with ≥2 OOB targets + form reset | ☐ |
| OOB fragments bake their own `id` + `hx-swap-oob` | ☐ |
| Mutation route registered **before** `mount_pages` | ☐ |

## What's next

- Run the full example: [[docs/examples/lucky-cat|Lucky Cat]] — SSE ticker, Suspense portfolio, auth gating, and the production `trade_store`.
- Deep dive forms: [[docs/build-apps/forms-data/forms-validation|Forms & Validation]].
- Stable live updates inside a boosted shell: [[docs/tutorials/view-transitions-oob|View Transitions + OOB]].
- Clone the reference tree: [`examples/chirpui/lucky_cat/README.md`](https://github.com/lbliii/chirp/blob/main/examples/chirpui/lucky_cat/README.md).
