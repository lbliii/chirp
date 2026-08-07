# Chirp Product Positioning

## Category

Chirp is a hypermedia-native Python framework for server-rendered product UIs.
It is a framework, not a template library or an SPA adapter: routes, typed return
values, named template blocks, and browser interactions form one checked system.

## Audience

Python developers building interactive product interfaces who want server-owned
HTML without duplicating pages into fragments, client state, and a separate API
architecture. It is especially useful when the interface is form-heavy, workflow
driven, realtime, or long-lived enough that the connection between a route and a
browser target must remain inspectable.

## Problem

The usual server-rendered path fragments the application: full-page templates,
partial templates, htmx targets, route strings, and test assumptions drift apart.
The usual SPA path duplicates the same product model across a JSON API and a
client application. In both cases, the browser receives an interaction whose
declarations are difficult to trace and validate together.

## Promise

**One template. Every interaction. Checked before deploy.**

One named-block template can serve full navigation, fragment swaps, streamed
HTML, and SSE updates. Typed returns declare the intended response; `chirp check`
validates the route, block, and target relationships before deployment.

## Pillars and proof

| Pillar | What it means | Source-backed proof |
| --- | --- | --- |
| One template, named blocks | Pages and partial updates share one template contract. | [`Page` and `Fragment`](../src/chirp/templating/returns.py), the [hypermedia model](../site/content/docs/about/core-concepts/hypermedia-model.md), and `uv run pytest tests/test_app/test_hypermedia_program.py -q`. |
| Types express interaction | Return types select a render surface without response plumbing. | [Return-type source](../src/chirp/templating/returns.py), the [return-value reference](../site/content/docs/about/core-concepts/return-values.md), and `uv run pytest tests/test_returns.py tests/test_response.py -q`. |
| Wiring is checked | Routes, blocks, and targets can be validated before deploy. | [`App.check()`](../src/chirp/app/__init__.py), the [`chirp check` handler](../src/chirp/cli/_milo_handlers.py), [contract categories](../site/content/docs/quality/contracts-debugging/categories.md), and `uv run pytest tests/contracts tests/test_cli_check.py -q`. |
| Live server rendering | The primary product is a live ASGI app, including streaming and SSE. | [`Suspense`](../src/chirp/templating/returns.py), [`EventStream`](../src/chirp/realtime/events.py), the [streaming and realtime guide](../site/content/docs/build-apps/streaming-updates/_index.md), and `uv run pytest tests/test_suspense.py tests/test_events.py tests/test_sse_integration.py -q`. |
| Optional layers stay optional | UI, forms, auth, data, and other extras do not redefine the core. | [Package extras](../pyproject.toml), [installation and extras](../site/content/docs/get-started/installation.md), and `uv run pytest tests/test_lazy_imports.py -q`. |

## Boundaries

- Chirp is alpha; do not describe every API, scaffold, or companion integration as stable.
- The primary output is live ASGI. `chirp freeze` is only a static projection for compatible routes.
- JSON routes and explicit `Response` objects are supported where they are the right boundary; Chirp does not require an all-or-nothing HTML claim.
- Free-threading evidence covers framework-owned paths under Python 3.14t, not application globals or untested optional integrations.
- HTTP QUERY is controlled early-adopter support: stable promotion and universal proxy/CDN support are **not** claimed.
- Background jobs, admin UIs, and email delivery remain integration boundaries, not core-product promises.

## Message hierarchy

1. **Promise:** One template. Every interaction. Checked before deploy.
2. **Category:** Hypermedia-native Python framework for server-rendered product UIs.
3. **Mechanism:** Typed returns and named blocks make the route-to-browser relationship explicit.
4. **Proof:** `chirp check`, the compiler architecture, and the Full-Application Journey.
5. **Practical result:** Interactive server-rendered interfaces without a parallel SPA or duplicate partial system.
6. **Boundary:** Alpha status and evidence-scoped production claims.

## Preferred terms

Prefer: “server-rendered product UI,” “hypermedia-native,” “named blocks,”
“typed return values,” “render surface,” “contract compiler,” “checked wiring,”
and “live ASGI application.”

Avoid: “full-stack replacement,” “zero JavaScript” (browser behavior may use
htmx), “production-proof” without scope, “thread-safe” without the framework
boundary, and claims that Chirp replaces every API, background-job, or admin tool.

## Reusable descriptions

**One sentence:** Chirp is a hypermedia-native Python framework that turns typed
route returns and named template blocks into checked server-rendered interactions.

**Short:** Build interactive Python product UIs from one template system. Chirp
renders pages, fragments, streams, and SSE updates from named blocks, then checks
the wiring before deploy.

**Long:** Chirp is a hypermedia-native Python framework for server-rendered
product UIs. Instead of splitting an interaction across page templates, partials,
browser targets, and a separate client app, it uses typed return values and named
blocks to make the render contract explicit. `chirp check` validates that contract
before users encounter a broken route or target.

## Hero rationale

The active weaverbird represents Chirp as an involved maker, not a mascot laid
over a generic scene. It weaves named template blocks through browser, fragment,
stream, and event paths in the same tactile screen-print family as the rest of
the personal-project stack. The setting should visibly carry the work: threads,
blocks, and pathways must connect to what the bird is making.

## Editorial standard

Apply a Zinsser-oriented standard: lead with the reader’s concrete problem and
the product’s observable result; use short, specific sentences; keep one thought
per paragraph; remove throat-clearing, stacked adjectives, and repeated claims.
Every strong architectural, performance, security, and production statement must
name its proof or a boundary. A README should be a useful front door, not an
encyclopedia; route details to the source-backed documentation.
