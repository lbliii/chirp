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

Use this example when you are deciding which return type to use. It puts every
major Chirp response shape on one page, with routes that demonstrate when each
type is appropriate.

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

Open `http://127.0.0.1:8000/` and click through the cards.

## Contract Surface

The example is useful for contract work because it deliberately exercises the
HTML surfaces Chirp protects: fragment block names, OOB targets, deferred
Suspense blocks, SSE fragment payloads, and validation fragments.

Run:

```bash
PYTHONPATH=src chirp check examples.standalone.returns_gallery.app:app
pytest examples/standalone/returns_gallery/
```

## Source

- [`app.py`](https://github.com/lbliii/chirp/blob/main/examples/standalone/returns_gallery/app.py)
- [`gallery.html`](https://github.com/lbliii/chirp/blob/main/examples/standalone/returns_gallery/templates/gallery.html)
- [`README.md`](https://github.com/lbliii/chirp/blob/main/examples/standalone/returns_gallery/README.md)

## Next

- [[docs/about/core-concepts/return-values|Return Values]]
- [[docs/build-apps/html-fragments/fragment-blocks|Fragment Blocks]]
- [[docs/build-apps/streaming-updates|Streaming]]
