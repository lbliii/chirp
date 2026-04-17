# RFC 002: Resolution as Data — The Next Ergonomic Leap

**Status:** Draft
**Author:** (proposal, following contract-test reliability work)
**Created:** 2026-04-17

---

## 1. The Thesis

Chirp already nailed the *what-to-return* story. `Template`, `Fragment`, `OOB`,
`Suspense`, `MutationResult`, `EventStream` — return-type-as-intent is a genuinely
novel abstraction, and the contract-test sprint (see
`docs/plan-contract-tests-reliability.md`) confirmed the top-level semantics hold.

What the contract-test work **also** surfaced is that behind each of those types
sits a small, silent **resolution engine** — a series of lookups and conditionals
that pick:

- Which render pipeline fires (full page? fragment? OOB re-assembly?)
- Which DOM node a fragment targets (registry? explicit? default?)
- Which swap strategy wins (registry default? explicit override? chirp fallback?)
- Which template and block name actually get rendered
- Whether middleware like `HTMLInject` or `AlpineInject` applies
- Whether response body is cacheable, injectable, streamable

Each individual decision is simple. Collectively they are hard to reason about —
every new test case during the sprint started with *"but how does this actually
resolve?"* and often ended with *"so there are two pipelines that behave
differently here"*.

The next leap: **make resolution a first-class value, not an emergent property.**

---

## 2. Evidence Gathered During Contract Tests

### 2.1 Two OOB pipelines, one error contract (now fixed)

Before PR #90, `render_fragment` called `template.render_block(name, ctx)` raw
and propagated kida's `KeyError`. The layout-region path (`register_oob_region`
→ `_render_oob_regions`) wrapped the same failure in `BlockNotFoundError`. Same
surface-level failure, two different exception types, two different messages.

**Fixed** in `src/chirp/templating/integration.py` by pre-checking
`template.list_blocks()` in `render_fragment` and raising `BlockNotFoundError`
from both paths.

**What this reveals:** the two pipelines exist because they were built at
different times for different purposes and never reconciled. `OOB(...)` is a
return-type; `register_oob_region` is an app-level declaration. They converge
on the same runtime operation (render block X of template Y as an OOB swap
targeting DOM id Z) but own separate resolution logic.

### 2.2 Cache poisoning via invisible cookie path (now fixed)

`CacheMiddleware` skipped caching when `response.headers` contained
`Set-Cookie`. It did **not** check `response.cookies` — the `with_cookie()`
API writes to a tuple which `sender.py` flattens into `Set-Cookie` headers
*after* middleware runs. So a handler returning
`Response(...).with_cookie("session", token)` would have its per-user cookie
cached and replayed to the next requester.

**Fixed** in `src/chirp/cache/middleware.py` by also checking
`not response.cookies`.

**What this reveals:** response state is currently spread across three places —
`response.body`, `response.headers`, `response.cookies` — and middleware has to
know to check all three. The serialization into the ASGI wire format is a
*separate* lifecycle stage. Middleware lives in the middle and has to guess.

### 2.3 Positional-fragment intent in `MutationResult`

```python
MutationResult(redirect="/next", primary_fragment, oob_fragment_a, oob_fragment_b)
```

The first `Fragment` positional arg is the primary swap; the rest are OOB. This
is documented nowhere in the signature — you have to read the code. During
Sprint 3, the test for "non-htmx request ignores fragments" had to *trust* that
`*fragments` meant the right thing.

**Gap:** intent is carried by position, not by shape.

### 2.4 `x-chirp-render-intent` is a load-bearing secret

`HTMLInject`, `AlpineInject`, and `SpeculationRulesInject` all gate on the
`x-chirp-render-intent` response header (values: `full_page`, `fragment`,
`unknown`). This header is the **real** public contract that separates "full
navigation" from "htmx swap", not `HX-Request` as most htmx middleware assumes.

It is not documented. The tests in Sprint 5 for "snippet absent on fragment
response" had to infer this from reading `returns.py` and the middleware.

**Gap:** an internal header acts as a public contract but has no spec.

### 2.5 `register_oob_region` duplicates silently overwrite

The matrix test in Sprint 2 proved that registering the same block twice
silently replaces the prior entry. No warning, no startup check. If two plugins
both register `"flash"`, the second wins without a peep.

**Gap:** setup-time conflicts should be visible at setup time.

### 2.6 OOB orphan validation has a discovery hole

`app.check()` validates `oob_registry` entries against layout templates, but
for non-pages-mounted apps the "layout templates" set is inferred heuristically.
Apps that construct HTML outside the pages hierarchy can register an OOB region
that points at a block no reachable template defines — and the check passes
because it had no layout to compare against.

**Gap:** the check's input is implicit; it should be declarable.

---

## 3. The Proposal — Resolution as Data

Instead of scattered conditionals, expose resolution as inspectable records.

### 3.1 `ResolutionPlan` — one object, one decision record

Every chirp response, before rendering, produces a `ResolutionPlan`:

```python
@dataclass(frozen=True)
class ResolutionPlan:
    intent: Literal["full_page", "fragment", "oob", "stream", "redirect"]
    primary: BlockSpec | TemplateSpec | None     # the main content
    oob_targets: tuple[OOBTarget, ...]            # with source: registry/explicit/default
    head_injections: tuple[HeadInjection, ...]    # speculation_rules, alpine, etc.
    body_injections: tuple[BodyInjection, ...]
    cache_eligible: bool                          # and why not, when False
    render_intent_header: str

@dataclass(frozen=True)
class OOBTarget:
    block_name: str
    template: str
    dom_id: str
    swap: str
    wrap: bool
    source: Literal["registry", "explicit_fragment", "default"]
```

A route handler returning `OOB(main, Fragment(...), Fragment(...))` produces a
plan. The render pipeline consumes the plan. Tests inspect the plan directly
without stringifying HTML.

### 3.2 Reshape `MutationResult` to name its parts

```python
# Before
MutationResult("/next", primary, oob_a, oob_b, trigger="saved")

# After
MutationResult(
    redirect="/next",
    primary=primary,
    oob=(oob_a, oob_b),
    trigger="saved",
)
```

Backwards-compatible via positional-arg deprecation shim for one release cycle.

### 3.3 Document `x-chirp-render-intent` as a public contract

Promote to `docs/contracts/render-intent.md`. Define the three values, their
semantics, and which middleware reads them. Third-party middleware authors need
this — right now they have to reverse-engineer it from `AlpineInject`.

### 3.4 `register_oob_region` becomes strict by default

```python
app.register_oob_region("flash", target_id="flash")
app.register_oob_region("flash", target_id="flash-2")
# RuntimeError at setup time: "OOB region 'flash' already registered"
```

Opt-out via `allow_override=True` for plugins that intentionally replace.
Same pattern as `app.add_route` vs `app.add_route(replace=True)`.

### 3.5 Declare layout templates explicitly

```python
app.declare_layout_templates(["_layout.html", "_auth_layout.html"])
```

Removes the heuristic. `app.check()` validates OOB regions against the declared
set. For pages-mounted apps, declaration is auto-populated from the
`_layout.html` discovery walk.

### 3.6 Injectable cache backend via config

```python
AppConfig(cache_backend=MemoryCacheBackend())
```

Today the cache middleware takes a backend in its constructor and every test
wires one up manually (`_wire_cache` helper). For apps, a config field is more
discoverable and plays with the config-freeze lifecycle.

---

## 4. What This Unlocks

### 4.1 Contract tests become schema-driven (the CommonMark insight)

CommonMark's `spec.json` is 632 rows of `{markdown, html}`. The reference
implementation is tested by running every row through the parser and diffing
HTML. Bugs become one-line additions to `spec.json`.

With `ResolutionPlan` as a first-class object, chirp's contract tests can
follow the same shape:

```json
{
  "input": {"return_value": "OOB", "args": {...}, "headers": {"HX-Request": "true"}},
  "expected_plan": {
    "intent": "oob",
    "oob_targets": [
      {"block_name": "flash", "dom_id": "flash", "swap": "innerHTML", "source": "registry"}
    ],
    "cache_eligible": false
  }
}
```

The contract suite becomes data; regressions become spec rows; plugins can ship
their own spec fragments.

### 4.2 Debug tooling gets trivial

A `/__chirp/resolve?url=/some/path` dev endpoint that renders the plan as JSON.
Plugin authors stop guessing which middleware fires in which order.

### 4.3 Middleware composition becomes auditable

`AlpineInject`, `HTMLInject`, and `SpeculationRulesInject` all currently sniff
the same header and the same response shape. With injections declared on the
plan, the render stage runs them in a deterministic order and a test can
assert *"for this route, the applied injections in order were: alpine,
speculation_rules"*.

### 4.4 Fewer footguns by construction

- Cookie-cache-poisoning class of bug: impossible if `cache_eligible` is a
  boolean on the plan rather than a scattered set of conditionals.
- OOB error contract divergence: impossible if both pipelines build
  `OOBTarget` records that go through one renderer.
- OOB orphan blocks: caught during plan construction, not during render.

---

## 5. Non-Goals

- **Not** a rewrite. The existing return types (`Template`, `Fragment`, etc.)
  stay exactly as they are. `ResolutionPlan` is an internal normalized form
  they compile down to.
- **Not** a new user-facing API for most apps. Route handlers keep returning
  what they return; the plan is plumbing.
- **Not** a typed-request-object revolution. Handlers still take `Request`
  and return values.

---

## 6. Staging

A realistic rollout, smallest-to-largest:

1. **Immediate** — land the two bug fixes from this sprint (cache cookies,
   OOB error contract). Done.
2. **Next** — introduce `ResolutionPlan` as an internal dataclass with no API
   change; have `OOB(...)` and `MutationResult(...)` build it; migrate the
   render pipeline to consume it.
3. **Then** — ship the `MutationResult(primary=, oob=)` shape with a
   positional-arg deprecation warning.
4. **Then** — publish the render-intent contract doc and stabilize the header.
5. **Later** — expose a `plan` field on the test-client response object so
   tests can assert on the plan directly; ship spec-JSON style fixtures.
6. **Later** — the strict `register_oob_region` default and layout declaration.

Each stage is independently shippable and independently reversible.

---

## 7. Open Questions

- Should `EventStream` produce a plan, or is its per-yield dynamism a reason
  to keep it plan-less? Likely plan-less at the response boundary, but each
  yielded `Fragment` gets its own (sub-)plan.
- `Suspense` shell vs deferred chunks: does the shell carry a plan that
  *references* the deferred sub-plans? Probably yes — that would let
  `__chirp_defer_pending__` be derived rather than threaded through context.
- Does the plan survive serialization (useful for caching, debuggers) or is
  it strictly in-memory? Leaning in-memory for v1.

---

## 8. Closing

The contract-test sprint proved the top-level abstractions are sound. The
next leap isn't another return type — it's making the resolution that **sits
beneath** those types a value instead of a procedure. Once resolution is data,
everything downstream (tests, debuggers, plugins, middleware, new response
types) gets cheaper.
