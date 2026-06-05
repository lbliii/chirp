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

## Chirp's Lane

Chirp is for Python teams building HTML-over-the-wire applications: full pages,
htmx fragments, streaming initial renders, and Server-Sent Events from the same
server-rendered templates.

The important difference is not "Chirp has htmx helpers." It is that Chirp
treats fragment navigation, OOB regions, Suspense blocks, SSE payloads, and
route-directory metadata as contracts the app can validate before users hit
broken UI.

## The Concrete Differentiator

In most Python stacks, htmx works because the application team maintains local
conventions:

- this link targets `#main`
- this form re-renders the `contact_form` block
- this response includes the cart badge as OOB
- this SSE event renders a block whose target exists in the page
- this boosted navigation path fits the current shell

Those conventions can work well, but they are usually invisible to the
framework. Chirp moves more of that wiring into typed return values,
registered regions, route metadata, and `app.check()`.

That gives Chirp its niche: fewer silent fragment failures, clearer debug
output, and one template that can safely serve full-page, fragment, OOB,
Suspense, and SSE access patterns.

## AI-Buildable by Construction

Most frameworks become "AI-buildable" by accumulating a large public corpus:
years of Stack Overflow answers, blog posts, and example repositories an LLM
can pattern-match against. Chirp does not have that corpus yet, and does not
depend on one.

Chirp's contracts are independent declarative invariants that name their own
fix. `app.check()` reports each issue with a stable **category** (the CI handle)
and a **message** that points at the concrete thing to change — the route,
template, block, selector, registration, config flag, or contract data. See the
[[docs/quality/contracts-debugging/categories|Contract Category Reference]]
preamble: "Treat the category as the stable handle for CI policy and the
message as the concrete fix target."

That structure lets an agent build correct Chirp apps from two things:

- the public-API surface (typed return values, registration calls, route
  metadata), and
- the contract errors, which describe the failure *and* the remedy.

The loop is mechanical: write a route, run `chirp check`, read the named fix,
apply it. The framework tells the model what is wrong and where, instead of
requiring the model to have memorized community lore. This is a different bet
than "wait for the corpus" — Chirp aims to be buildable from its own
self-describing surface.

- **Accessibility as a contract, not a claim.** Chirp ships five static
  accessibility checks — `a11y_interactive`, `a11y_label`, `a11y_alt`,
  `a11y_heading`, `a11y_landmark` — that run inside `app.check()` against your
  templates. Many frameworks *say* they support accessible UI; Chirp validates
  concrete a11y affordances at startup and names the fix, so an agent (or a
  human) gets the same actionable signal.

This positions Chirp **alongside** existing platforms rather than replacing
them. Chirp is narrower than Django on purpose: keep Django's admin, ORM, and
auth ecosystem where they fit, and let Chirp own the hypermedia UI surface with
self-describing contracts an LLM can build against.

## Compared With Python Frameworks

| Framework | Better fit | Chirp difference |
| --- | --- | --- |
| Flask | Small WSGI apps, broad extension ecosystem, familiar Jinja patterns | Chirp is ASGI-first, htmx-aware, and validates fragment/template wiring that Flask apps usually express as conventions. |
| FastAPI | JSON APIs, OpenAPI, Pydantic models, typed API clients | Chirp is HTML-first. Use FastAPI when the primary product surface is JSON; use Chirp when the primary surface is server-rendered UI. |
| Django | Batteries-included apps, ORM/admin/auth ecosystem, long-term stability | Chirp is narrower and more explicit: it focuses on hypermedia UI, typed return values, streaming, and contract checks rather than a full application platform. |
| Starlette | Low-level ASGI services and toolkit composition | Chirp builds a higher-level server-rendered UI model on top of ASGI concepts: templates, fragments, return types, contracts, and DevTools. |

## Compared With Hypermedia UI Stacks

| Stack | Better fit | Chirp difference |
| --- | --- | --- |
| htmx alone | Any backend that returns HTML and wants client-side attributes | Chirp gives Python-specific return types, template block rendering, and startup checks for the htmx surface. |
| Rails + Hotwire | Rails apps with Turbo, Action Cable, Active Record, and Rails conventions | Chirp is Python-native and htmx-oriented; it uses return types and Kida blocks instead of Turbo Stream tags and Rails responders. |
| Laravel Livewire | Laravel/PHP apps that want reactive components with minimal JavaScript | Chirp stays stateless-by-default HTML over HTTP; it does not hydrate server-side component state into every interaction. |
| Phoenix LiveView | Stateful realtime UI on Elixir processes and Phoenix channels | Chirp keeps normal HTML responses central, with `Suspense` for initial streaming and `EventStream` for post-load updates. |

## Use Chirp When

- You are building an htmx-driven app where the server owns rendered HTML.
- One template should serve full pages, fragment swaps, OOB updates, and SSE payloads.
- Startup validation of routes, targets, blocks, layouts, and shell contracts matters.
- Streaming initial render and post-load SSE are core product surfaces.
- Python 3.14 and free-threading readiness are part of the technical bet.
- You want a focused framework instead of a batteries-included platform.

## Choose Something Else When

- The product is primarily a JSON API: choose FastAPI or another API-first framework.
- You need Django's admin, ORM, ecosystem, and long-term compatibility story.
- You need WSGI hosting or older Python versions.
- You want a client-side SPA with a JSON serialization boundary.
- You want server-side reactive component state as the core model: Livewire or LiveView may fit better.
- You need the broadest plugin ecosystem more than tight hypermedia contracts.

## Useful Comparisons

- [Flask docs](https://flask.palletsprojects.com/en/stable/) show the classic lightweight Python web model.
- [FastAPI docs](https://fastapi.tiangolo.com/tutorial/) show the API-first typed Python model.
- [Django docs](https://docs.djangoproject.com/en/6.0/) show a mature batteries-included documentation and framework surface.
- [htmx docs](https://htmx.org/docs/) explain the browser-side hypermedia model Chirp builds around.
- [Hotwire Turbo Streams](https://hotwire.io/documentation/turbo/handbook/streams) show a related server-rendered fragment-update model.
- [Phoenix LiveView](https://hexdocs.pm/phoenix_live_view/Phoenix.LiveView.html) shows the stateful realtime UI alternative.

## Next Steps

- [[docs/get-started/first-fragment-app|First Fragment App]] — Try the smallest complete htmx-backed Chirp app
- [[docs/about/core-concepts/return-values|Return Values]] — Learn the type-driven response model
- [[docs/quality/contracts-debugging/debugging-swaps|Debugging Swaps]] — See how `chirp check` and DevTools catch broken UI wiring
