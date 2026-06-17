---
title: Returns Gallery
description: Every Chirp return type on one page
draft: false
weight: 20
lang: en
type: doc
tags: [examples, return-values, fragments, streaming]
keywords: [returns gallery, template, page, fragment, oob, suspense, stream, eventstream]
category: examples
---

## What It Teaches

Chirp expresses intent through the value a handler returns: the
[[docs/about/core-concepts/return-values|return type]] picks the response shape.
This runnable example puts every return type on one page so you can see, side by
side, which one to reach for. Browse the table to pick a shape, then read its
route in `app.py` for a one-paragraph "use when".

:::{tip} New to the model?
Read the [[docs/about/core-concepts/return-values|return-values decision tree]]
first — it explains *why* each type exists. This page is the
copy-from-working-code companion: you pick a shape and lift the route.
:::

| Route | Return type | Use when |
| --- | --- | --- |
| `GET /` | `Template` | Full-page render with no htmx negotiation |
| `GET /fragment` | `Fragment` | A named block is always the response |
| `GET /page` | `Page` | Browser requests need a full page; htmx requests need a block |
| `POST /oob` | `OOB` | One action updates multiple targets |
| `GET /stream` | `Stream` | A response can flush sections as they complete |
| `GET /suspense` | `Suspense` | Initial render needs a shell first, then deferred blocks |
| `GET /events` | `EventStream` | Post-load updates should arrive over SSE |
| `POST /validate` | `ValidationError` | Invalid form data should re-render a 422 fragment |
| `POST /mutate` | `MutationResult` | One mutation supports multiple UX flows |
| `GET /redirect` | `Redirect` | The browser should navigate elsewhere |

## Run It

```bash
PYTHONPATH=src python examples/standalone/returns_gallery/app.py
```

Open `http://127.0.0.1:8000/` and click through the cards. Hit the same URLs
with an `HX-Request` header to watch content negotiation pick the fragment over
the full page.

## What a route looks like

Each route returns a different type and carries a docstring naming when to reach
for it. `Page` is the workhorse — one URL that serves a full page to browsers and
a [[docs/build-apps/html-fragments/fragment-blocks|named block]] to htmx:

```python
@app.route("/page", name="page")
def page_demo():
    """Page — fragment for htmx requests, full page for browser navigation.

    Use when: the same URL must serve both a standalone page and an htmx
    swap. Same template, same data, the framework picks the right shape
    based on the HX-Request header.
    """
    return Page("gallery.html", "demo_page", value=random.randint(1, 100))
```

*Source: [`examples/standalone/returns_gallery/app.py`](https://github.com/lbliii/chirp/blob/main/examples/standalone/returns_gallery/app.py).*

`Template`, `Fragment`, `Page`, `OOB`, `ValidationError`, and `MutationResult`
all render against one template — `templates/gallery.html`, a single file of
named blocks. `Stream` and `Suspense` each render their own full document, so
they use side templates (`gallery_stream.html`, `gallery_suspense.html`).
`EventStream` ([[docs/build-apps/streaming-updates/server-sent-events|SSE]]) is a
post-load channel with no shell of its own.

:::{dropdown} Advanced: use it for contract work
This example deliberately exercises the HTML surfaces Chirp protects — fragment
block names, OOB targets, deferred Suspense blocks, SSE fragment payloads, and
validation fragments — so it doubles as a fixture for contract checks.

```bash
PYTHONPATH=src chirp check examples.standalone.returns_gallery.app:app
pytest examples/standalone/returns_gallery/
```

See [[docs/quality/contracts-debugging/categories|contract categories]] for what
each check enforces.
:::{/dropdown}

## Source

- [`app.py`](https://github.com/lbliii/chirp/blob/main/examples/standalone/returns_gallery/app.py)
- [`gallery.html`](https://github.com/lbliii/chirp/blob/main/examples/standalone/returns_gallery/templates/gallery.html)
- [`README.md`](https://github.com/lbliii/chirp/blob/main/examples/standalone/returns_gallery/README.md)

:::{note} See also
- [[docs/about/core-concepts/return-values|Return Values]] — the decision tree and the *why*
- [[docs/build-apps/html-fragments/fragment-blocks|Fragment Blocks]] — named-block mechanics
- [[docs/build-apps/streaming-updates/_index|Streaming Updates]] — `Stream`, `Suspense`, `EventStream`
:::
