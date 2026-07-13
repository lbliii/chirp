---
title: When to Use Chirp
description: When Chirp fits, how it differs from mainstream Python and hypermedia frameworks, and when to choose alternatives
draft: false
weight: 30
lang: en
type: doc
tags: [choosing, features]
keywords: [python web framework, htmx framework, fragments, streaming, flask alternative]
category: explanation
---

## What Chirp is

Chirp is a hypermedia-native application framework for server-rendered Python
UIs. It sends full pages, htmx fragments, streaming renders, and live updates
instead of using JSON as a mandatory boundary to a JavaScript front end.

Reach for Chirp when server-rendered UI is your main product surface and you
want the framework to catch broken UI wiring before users do. Reach for
something else when your product is primarily a JSON API or a client-side SPA.

The one-line differentiator: Chirp expresses each response as a typed return
value, and `app.check()` validates the htmx surface — fragment targets, OOB
regions, deferred blocks, SSE blocks — at startup. A *fragment* is a named
slice of a template returned on its own; an *OOB* (out-of-band) swap updates a
second region in the same response; *SSE* is the long-lived event channel that
pushes updates after the page loads. You can learn the full mapping in
[[docs/about/core-concepts/return-values|the return-type-is-intent model]].

## How Chirp compares

Two questions decide most evaluations: *Which Python framework is this instead
of?* and *Which hypermedia stack does it replace?* Use the better-fit column to
rule Chirp out fast, and the difference column to see what it adds.

### Against Python frameworks

:::{list-table}
:header-rows: 1

* - Framework
  - Better fit when
  - What Chirp does differently
* - **Flask**
  - Small WSGI apps, a broad extension ecosystem, familiar Jinja patterns.
  - ASGI-first and htmx-aware; validates fragment and template wiring that Flask apps express as informal conventions.
* - **FastAPI**
  - JSON APIs, OpenAPI, Pydantic models, typed API clients.
  - HTML-first. Use FastAPI when the product surface is JSON; use Chirp when it is server-rendered UI.
* - **Django**
  - Batteries-included apps, the ORM/admin/auth ecosystem, long-term stability.
  - Narrower and more explicit: hypermedia UI, typed return values, streaming, and contract checks rather than a full application platform.
* - **Starlette**
  - Low-level ASGI services and toolkit composition.
  - A higher-level server-rendered UI model on top of ASGI: templates, fragments, return types, contracts, and DevTools.
:::

:::{note}
Chirp is narrower than Django on purpose. Keep Django's admin, ORM, and auth
ecosystem where they fit, and let Chirp own the server-rendered product UI.
Chirp is an application framework, but not a kitchen-sink application platform.
:::

### Against hypermedia UI stacks

:::{list-table}
:header-rows: 1

* - Stack
  - Better fit when
  - What Chirp does differently
* - **htmx alone**
  - Any backend that returns HTML and wants client-side attributes.
  - Adds Python-specific return types, template-block rendering, and startup checks for the htmx surface.
* - **Rails + Hotwire**
  - Rails apps with Turbo, Action Cable, Active Record, and Rails conventions.
  - Python-native and htmx-oriented; uses return types and Kida blocks instead of Turbo Stream tags and Rails responders.
* - **Laravel Livewire**
  - Laravel/PHP apps that want reactive components with minimal JavaScript.
  - Stateless-by-default HTML over HTTP; does not hydrate server-side component state into every interaction.
* - **Phoenix LiveView**
  - Stateful realtime UI on Elixir processes and Phoenix channels.
  - Keeps normal HTML responses central, with [[docs/build-apps/streaming-updates/html-streaming|Suspense for initial streaming]] and [[docs/build-apps/streaming-updates/server-sent-events|EventStream for post-load updates]].
:::

## Use Chirp when

- You are building an htmx-driven app where the server owns rendered HTML.
- One template should serve full pages, fragment swaps, OOB updates, and SSE payloads.
- Startup validation of routes, targets, blocks, layouts, and shell contracts matters.
- Streaming initial render and post-load SSE are core product surfaces.
- Python 3.14 and free-threading are part of your technical bet.
- You want a focused framework instead of a batteries-included platform.

## Choose something else when

- The product is primarily a JSON API — choose FastAPI or another API-first framework.
- You need Django's admin, ORM, ecosystem, and long-term compatibility story.
- You need WSGI hosting or older Python versions.
- You want a client-side SPA with a JSON serialization boundary. That boundary
  has a recurring cost: the server hand-builds a config blob the client fetches
  on boot, and re-states every flag again as a read/write API — see the
  [[docs/about/core-concepts/hypermedia-model#no-client-config-blob-to-keep-in-sync|no-client-config-blob side-by-side]]
  for what that drift looks like and what Chirp does instead.
- You want server-side reactive component state as the core model — Livewire or LiveView may fit better.
- You need the broadest plugin ecosystem more than tight hypermedia contracts.

For the full list of what Chirp deliberately does not do, see
[[docs/about/non-goals|the honest non-goals]].

::::{dropdown} Why Chirp is buildable from its own surface
Most frameworks become "AI-buildable" by accumulating a large public corpus:
years of Stack Overflow answers, blog posts, and example repositories an LLM
can pattern-match against. Chirp does not have that corpus, and does not depend
on one.

`app.check()` reports each issue with a stable **category** (the CI handle) and
a **message** that points at the concrete thing to change — the route, template,
block, selector, registration, or config flag. The
[[docs/quality/contracts-debugging/categories|contract category reference]]
states the rule directly: treat the category as the stable handle for CI policy
and the message as the concrete fix target.

That makes the build loop mechanical: write a route, run `chirp check`, read the
named fix, apply it. An agent (or a human) builds correct Chirp apps from two
things — the public-API surface and the contract errors, which describe the
failure *and* the remedy — instead of memorized community lore. The published
docs site also emits [`/chirp/llms.txt`](/chirp/llms.txt) on build for machine-readable navigation.

:::{since} 0.8.0
Accessibility is one of those contracts. Chirp ships five
[[docs/build-apps/ui-extensions/accessibility|static accessibility checks]] —
`a11y_interactive`, `a11y_label`, `a11y_alt`, `a11y_heading`, and
`a11y_landmark` — that run inside `app.check()` against your templates. They
validate concrete a11y affordances at startup and name the fix, rather than
claiming support.
:::
::::{/dropdown}

:::{note} See also

- [Flask docs](https://flask.palletsprojects.com/en/stable/) — the classic lightweight Python web model.
- [FastAPI docs](https://fastapi.tiangolo.com/tutorial/) — the API-first typed Python model.
- [Django docs](https://docs.djangoproject.com/en/6.0/) — a mature batteries-included framework surface.
- [htmx docs](https://htmx.org/docs/) — the browser-side hypermedia model Chirp builds around.
- [Hotwire Turbo Streams](https://hotwire.io/documentation/turbo/handbook/streams) — a related server-rendered fragment-update model.
- [Phoenix LiveView](https://hexdocs.pm/phoenix_live_view/Phoenix.LiveView.html) — the stateful realtime UI alternative.
:::

## Next steps

- [[docs/get-started/first-fragment-app|First Fragment App]] — try the smallest complete htmx-backed Chirp app.
- [[docs/about/core-concepts/return-values|Return Values]] — learn the type-driven response model.
- [[docs/quality/contracts-debugging/debugging-swaps|Debugging Swaps]] — see how `chirp check` and DevTools catch broken UI wiring.
