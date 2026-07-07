---
title: Assertions
description: Assert on the shape of a hypermedia response — fragment vs page, HX-* headers, OOB targets, SSE events
draft: false
weight: 20
lang: en
type: doc
tags: [testing, assertions, fragments, sse, htmx]
keywords: [assertions, fragment, sse, testing, htmx, oob, headers, helpers]
category: guide
---

## Overview

Chirp ships assertion helpers that check the *shape* of a hypermedia response — is it a [[docs/build-apps/html-fragments/fragments|fragment]] or a full page, does it carry the right `HX-*` header, does it contain the expected out-of-band (OOB) swap targets. Your tests assert on intent, not on brittle substring matching.

Import them from `chirp.testing` and pair them with a [[docs/quality/testing/test-client|TestClient]]:

```python
from chirp.testing import TestClient, assert_is_fragment, assert_hx_redirect
```

Reach for these whenever a plain `assert "x" in response.text` would miss the thing that actually matters: the response *type*, the htmx headers, or the OOB targets a fragment response carries.

## The assertion family at a glance

Seventeen helpers, grouped by the job they do. Find the one you need, then jump to the example below.

:::{list-table}
:header-rows: 1

* - Job
  - Helpers
* - **Fragment shape** — is this a partial or a full page?
  - `assert_is_fragment` · `assert_is_full_page` · `assert_no_full_document` · `assert_fragment_contains` · `assert_fragment_not_contains` · `assert_is_error_fragment` · `assert_has_id`
* - **htmx headers** — did the response steer the client?
  - `hx_headers` · `assert_hx_redirect` · `assert_hx_push_url` · `assert_hx_trigger` · `assert_hx_retarget` · `assert_hx_reswap`
* - **OOB + mutation** — did a write land its swaps?
  - `assert_oob_targets` · `assert_mutation_fragments` · `assert_mutation_redirect`
* - **Status**
  - `assert_status`
:::

## Minimal working example

The most common check: a route returns a full page for a browser and a fragment for htmx.

```python
from chirp.testing import TestClient, assert_is_fragment, assert_is_full_page

async def test_search_negotiates():
    async with TestClient(app) as client:
        # Browser navigation -> full page
        page = await client.get("/search")
        assert_is_full_page(page)

        # htmx request -> fragment
        fragment = await client.fragment("/search?q=python")
        assert_is_fragment(fragment)
```

`assert_is_fragment` checks three things: the status is `200` (override with `status=`), the body has no `<html>`/`</html>` wrapper, and the body is non-empty. `assert_is_full_page` checks for an `<html>` tag or a doctype. `client.fragment(...)` sets the `HX-Request` header for a narrow swap; use `client.boosted(..., target="main")` for shell navigation — see the [[docs/quality/testing/test-client|TestClient]] guide.

## Common patterns

### Assert on fragment content

```python
from chirp.testing import assert_fragment_contains, assert_fragment_not_contains

async def test_search_results():
    async with TestClient(app) as client:
        response = await client.fragment("/search?q=apple")
        assert_fragment_contains(response, "apple")
        assert_fragment_contains(response, '<div id="results">')
        assert_fragment_not_contains(response, "banana")
```

### Assert an error fragment

`assert_is_error_fragment` matches the `chirp-error` CSS class that Chirp's error fragments carry. Pass `status=` to also assert the HTTP status and the matching `data-status` attribute.

```python
from chirp.testing import assert_is_error_fragment

async def test_missing_item():
    async with TestClient(app) as client:
        response = await client.fragment("/items/9999")
        assert_is_error_fragment(response, status=404)
```

### Assert htmx headers

When a handler steers the client with `HX-Redirect`, `HX-Push-Url`, or an `HX-Trigger` event, assert on the header rather than scraping the body.

```python
from chirp.testing import assert_hx_redirect, assert_hx_trigger

async def test_login_redirects():
    async with TestClient(app) as client:
        response = await client.post("/login", data={"user": "alice", "pass": "secret"})
        assert_hx_redirect(response, "/dashboard")
        assert_hx_trigger(response, "login-success")
```

:::{tip} Header casing is normalized for you
`hx_headers(response)` returns a dict keyed by canonical htmx casing (`HX-Push-Url`), even though the ASGI layer lowercases header names on the wire. Assert on `headers["HX-Push-Url"]` and stop worrying about `hx-push-url` vs `HX-Push-Url`.
:::

`assert_hx_trigger(..., after="swap" | "settle")` proves htmx 2/generic wire
encoding only. A passing header assertion does not prove browser delivery in
htmx 4, which removed both timing headers. Test the rendered data marker and
the target's `htmx:before:settle` or `htmx:after:settle` event in a browser.

### Assert OOB swaps and mutation results

A mutation that returns `OOB(...)` writes several swap targets into one response. `assert_oob_targets` confirms each `hx-swap-oob` target is present. For a route built on `FormAction`/`MutationResult`, `assert_mutation_fragments` checks the htmx path (200 + OOB targets) and `assert_mutation_redirect` checks the plain-POST path (a `303` redirect by default).

```python
from chirp.testing import assert_mutation_fragments, assert_mutation_redirect

async def test_save_item():
    async with TestClient(app) as client:
        # htmx POST -> inline OOB swaps
        htmx = await client.fragment("/items/save", method="POST")
        assert_mutation_fragments(htmx, "item-row", "count")

        # plain POST -> redirect
        plain = await client.post("/items/save")
        assert_mutation_redirect(plain, "/items")
```

If a swap target never appears in the DOM you expect, the failure message lists the OOB ids it *did* find — see [[docs/quality/contracts-debugging/debugging-swaps|debugging swaps]] and the [[docs/quality/contracts-debugging/oob-registry|OOB registry]].

## SSE testing

Collect events from a [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]] endpoint with `client.sse()` and assert on the structured result, never on the raw `text/event-stream` bytes.

```python
async def test_notifications():
    async with TestClient(app) as client:
        result = await client.sse("/notifications", max_events=3)

        assert result.status == 200
        assert len(result.events) == 3
        assert "notification" in result.events[0].data
```

:::{warning} Bound every SSE test
A long-lived stream never closes on its own. Always pass `max_events` (collect *N* data events) or `disconnect_after` (collect for *N* seconds), or the test will hang. `client.sse()` defaults to `max_events=10`; `timeout` is an alias for `disconnect_after`, and passing both raises `TypeError`.
:::

`client.sse()` returns a frozen `SSETestResult`:

:::{list-table}
:header-rows: 1

* - Field
  - Type
  - Description
* - `events`
  - `tuple[SSEEvent, ...]`
  - Collected data events, in order.
* - `heartbeats`
  - `int`
  - Count of heartbeat comment frames.
* - `status`
  - `int`
  - HTTP status from the stream's response start.
* - `headers`
  - `dict[str, str]`
  - Response headers.
:::

Each `SSEEvent` carries `data: str`, `event: str | None`, `id: str | None`, and `retry: int | None`. Filter by event type to assert a typed channel fired:

```python
async def test_typed_events():
    async with TestClient(app) as client:
        result = await client.sse("/events", max_events=5)
        joins = [e for e in result.events if e.event == "user-join"]
        assert len(joins) >= 1
```

## Full assertion reference

:::{dropdown} Full assertion reference
The exact behavior of every helper. All import from `chirp.testing`.

**Fragment shape**

- `assert_is_fragment(response, *, status=200)` — status matches, no `<html>`/`</html>` wrapper, body non-empty.
- `assert_is_full_page(response, *, status=200)` — status matches, body contains `<html` or a doctype.
- `assert_no_full_document(response)` — body has no `<html` tag and no doctype (an htmx response that should *not* have returned a full document).
- `assert_fragment_contains(response, text)` / `assert_fragment_not_contains(response, text)` — substring presence/absence.
- `assert_is_error_fragment(response, *, status=None)` — body has the `chirp-error` class; with `status=`, also checks the HTTP status and a `data-status="<status>"` attribute.
- `assert_has_id(response, element_id)` — body contains an element with `id="element_id"`.

**htmx headers**

- `hx_headers(response) -> dict[str, str]` — all `HX-*` headers, keys normalized to canonical htmx casing.
- `assert_hx_redirect(response, url)` — `HX-Redirect` equals `url`.
- `assert_hx_push_url(response, url)` — `HX-Push-Url` equals `url`.
- `assert_hx_retarget(response, selector)` — `HX-Retarget` equals `selector`.
- `assert_hx_reswap(response, strategy)` — `HX-Reswap` equals `strategy`.
- `assert_hx_trigger(response, event, *, after=None)` — `HX-Trigger` contains the event (string match, or membership in a JSON payload, or exact dict equality). Pass `after="settle"` or `after="swap"` to assert `HX-Trigger-After-Settle` / `HX-Trigger-After-Swap` instead.

**OOB + mutation**

- `assert_oob_targets(response, *target_ids)` — each id appears with an `hx-swap-oob` attribute (matches either attribute order). Failure lists the ids that *were* found.
- `assert_mutation_fragments(response, *target_ids)` — status `200` and (if ids given) the OOB targets are present. The htmx-request shape of a `MutationResult`.
- `assert_mutation_redirect(response, url, *, status=303)` — redirect status (default `303`) and `Location` equals `url`. The plain-POST shape of a `MutationResult`.

**Status**

- `assert_status(response, status)` — exact status code match.
:::{/dropdown}

## See also

:::{note} See also
- [[docs/quality/testing/test-client|TestClient]] — make requests and read `status` / `text` / `headers`
- [[docs/build-apps/html-fragments/fragments|Fragments]] — what a fragment response is
- [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]] — what `client.sse()` consumes
- [[docs/quality/contracts-debugging/oob-registry|OOB registry]] — register and validate OOB swap targets
- [[docs/quality/contracts-debugging/debugging-swaps|Debugging swaps]] — when a swap target never lands
:::

:::{related}
:::
