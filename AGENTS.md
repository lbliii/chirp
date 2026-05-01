# AGENTS.md

Chirp renders the HTML that end users actually see. A bug in a return type, an OOB swap, or a Suspense block doesn't corrupt a database — it corrupts trust. The user clicks Save, the row vanishes from view, and the app dev has to explain why. They can't audit Chirp; they only see the gap. Treat the rules below as safety rules, not style rules.

---

## North star

**The server renders HTML, the browser renders UI, and the return type connects them.** Chirp exists so Python developers can build hypermedia-native apps without an SPA, an API serialization layer, or a JavaScript build pipeline. Every decision routes back to that: a single template serving full pages, fragments, SSE payloads, and Suspense blocks; intent expressed as types, not config; contracts validated before they reach a user. If a change fights that model, it isn't worth shipping.

---

## Design philosophy

- **The return type is the architecture.** `Page`, `Fragment`, `OOB`, `EventStream`, `Suspense`, `ValidationError`, `FormAction`, `MutationResult` — the type drives content negotiation, htmx-awareness, status codes, and streaming. There is no `make_response()` and no `jsonify()`. If you find yourself reaching for one, you're solving the wrong problem.
- **Three streaming types, three jobs.** `Stream` flushes blocks as they complete inside one chunked HTTP response (use for slow first-byte pages with independent sections). `Suspense` ships the shell first with `None` placeholders and streams deferred blocks as htmx OOB swaps inside one response (use for dashboards with multiple slow data sources). `EventStream` is SSE — a long-lived channel for updates *after* the page is loaded (notifications, tickers, chat tails). Picking wrong is the most common return-type mistake. If you're hesitating between Suspense and EventStream, ask "is this the initial render or a post-load update?" — Suspense for initial, EventStream for post-load.
- **One template, many access patterns.** A template with named blocks serves as full page, htmx fragment, SSE event payload, and Suspense deferred block. Don't split into a "partials" directory. Don't introduce a serialization layer. The block is the unit.
- **Frozen by default.** `AppConfig`, all return types, `ValidationResult`, `FreezeResult`, registry entries — `@dataclass(frozen=True, slots=True)`. Thread-safe by construction matters because we run on free-threaded Python. Mutability is a deliberate choice with a `threading.Lock`, not a default.
- **Contracts, not conventions.** `app.check()` validates the hypermedia surface at startup: routes, fragments, SSE references, OOB regions, layout scope. If you add a new way to render or wire HTML, add the check that catches it being wrong. Discoverability beats documentation. In debug mode this runs automatically on `app.run()`/`app.freeze()` and exits on ERROR — agents don't have to remember to invoke it. Disable with `AppConfig(skip_contract_checks=True)` or `CHIRP_SKIP_CONTRACT_CHECKS=1` only when you understand what you're turning off.
- **DevTools are opt-in, but agent-readable.** When debugging htmx swaps, OOB regions, Suspense blocks, SSE, fragment targets, or content negotiation, run with `debug=True` first (`chirp dev app:app`, temporary `AppConfig(debug=True)`, or `CHIRP_DEBUG=1` for apps using `AppConfig.from_env()`). Open the app in a browser, press `Ctrl+Shift+D`, and inspect `window.ChirpHtmxDebug.help()` / `window.ChirpHtmxDebug.exportRecordsJson()` before guessing from screenshots.
- **Fail loud.** Missing OOB blocks raise `BlockNotFoundError`. Orphan registry entries are ERROR at freeze. Silent empty swaps wipe live DOM — a user sees a blank section and assumes data was lost. Don't paper over a typo with `optional=True`; fix the layout or the registration.
- **Composition, not inheritance, for layouts.** Page templates are injected into the layout's `{% block content %}` via `render_with_blocks`. Page templates **cannot** override sibling layout blocks like `page_scripts` or `head_extra`. If you're tempted to "just let pages extend the layout" — stop. That breaks the model and the checks won't catch every regression.
- **Sharp edges are bugs.** Silent `except`, `# type: ignore`, ambiguous flags, error messages that don't tell the reader what to do next — not taste, bugs. Ruff/ty catch some; the rest is on you.

---

## Stakes

When you change something in Chirp, the blast radius is:

- **Return-type bugs** → wrong status code, wrong content negotiation, htmx fragment served as full page. Harm: an htmx swap pastes an entire `<html>` document into a `<div>`. The app looks broken to the user; the dev has no idea why.
- **OOB / Suspense rendering bugs** → silent empty swaps, deferred blocks that never resolve, ancestor blocks emitted as OOB chunks targeting non-existent ids. Harm: parts of the UI go blank mid-interaction. There is no error in the console. Users assume data was destroyed.
- **SSE error handling** → a single bad event closes a stream that was supposed to last for hours. Harm: a real-time dashboard goes silent and nobody notices until the on-call gets paged. Per-event boundaries exist for a reason — don't widen them.
- **Free-threaded races** → no GIL safety net on 3.14t. Mutable shared state in middleware, registries, or context will corrupt requests across threads. Chirp is one of the apps proving free-threading is real; a race we ship damages that case for everyone downstream.
- **`app.check()` regressions** → contracts that used to catch broken hypermedia stop catching it. The bug ships to a real app. Coverage of the check matters as much as the framework code.
- **`chirp freeze` (SSG) bugs** → wrong relative URLs, missing search index entries, broken OOB regions in static output. Harm: the docs site (or a customer's static site) ships with broken links and nothing in the browser tells them.

Chirp is pre-1.0 but powering real apps (including its own docs). Calibrate accordingly.

---

## Who reads your output

- **App devs writing routes.** They read tracebacks, error messages, `chirp check` output, and the type of whatever they returned. If they have to read Chirp source to figure out why their fragment didn't swap, we failed.
- **Ops / freezers.** They run `chirp freeze` in CI and read the output. Errors must be actionable: which template, which block, which registration.
- **Plugin authors** (chirp-ui, future ext modules). They read protocols (`ChirpPlugin`, `ContractCheck`, `Middleware`) and the surface of `app.register_*` / `app.set_*`. Stable shapes matter more than ergonomic shortcuts.
- **Contributors.** They know htmx and ASGI but not our internals. They read the return-type module, the render plan, and the contract checks.
- **Me (Lawrence).** I read diffs. Put the *what* in code, the *why* in the PR.

---

## Escape hatches — stop and ask

Forks where I want a check-in, not a judgment call:

- **New return type.** The list (`Page`, `Fragment`, `OOB`, `Suspense`, `EventStream`, `ValidationError`, `FormAction`, `MutationResult`, `Action`, `Stream`, `Redirect`) is load-bearing. Adding one means new content-negotiation rules, new contract checks, new docs, new tests. Sketch the case and ask first.
- **New `AppConfig` field.** The surface is already wide. Reshape an existing field before adding one. Configs are easier to add than to remove.
- **Touching the render pipeline** (`templating/render_plan.py`, `templating/returns.py`, Suspense block discovery, ancestor pruning). Sketch the change. These have subtle invariants — falsy `None`, `__chirp_defer_pending__`, `BlockNotFoundError` propagation — that are easy to break in ways tests don't catch.
- **Changing `app.check()` semantics.** Promoting WARNING → ERROR breaks people's CI. Demoting ERROR → WARNING hides bugs. Either way, ask, and use `app.override_contract_severity` as the user-facing escape valve before touching defaults.
- **Public API change** to App, return types, `ServerConfig`-equivalent, CLI, or registered protocol shapes. Migration cost is real; ask whether the break is worth it.
- **Adding a runtime dependency.** Chirp's optional-extra story is deliberate (`forms`, `sessions`, `auth`, `markdown`, `ui`, `redis`, `data-pg`, `ai`). New mandatory deps need a strong case; new extras need a name and a use case.
- **Touching the sync fast path** (`App.handle_sync`, `SyncRequest`, pre-encoded content types). Performance numbers are load-bearing; show before/after if you change anything here.
- **Free-threaded shared state.** Any new mutable singleton, registry, or cache. Sketch the locking story and ask before implementing.
- **Dead code you found.** Flag it in the PR; don't delete silently. It might be load-bearing for an example app, an extension, or a documented escape hatch.
- **Test disagrees with code.** Ask which is authoritative before "fixing" either. Contract tests in particular encode intentional behavior.
- **Can't reproduce a reported bug.** Stop. Ask for a minimal repro or env dump. Don't guess.
- **Adjacent issues found mid-task.** List in the PR description. Don't fold them in. Exception: refactors renaming a concept across many files — one bundled PR beats review churn.

---

## Scoped stewards

Root `AGENTS.md` is the constitution. It explains the project thesis, safety rules, and review
bar. Nested `AGENTS.md` files are local steward notes: they define the package boundary, what that
domain protects, and the checks that give the fastest signal for that slice.

- When editing a subtree, read the nearest `AGENTS.md` before changing files there.
- When a change spans multiple subtrees, read each affected steward file and include short
  **Steward Notes** in the PR description.
- Scoped steward files do not override this root guidance. If they disagree, root wins and the
  nested file should be fixed.
- Keep steward notes lightweight. They are there to sharpen judgment, not create process theatre.

Current steward map:

| Domain | Steward file |
| --- | --- |
| Public API, config, top-level errors, plugins | `src/chirp/AGENTS.md` |
| App lifecycle, freeze, registries, mounting | `src/chirp/app/AGENTS.md` |
| HTTP primitives and request/response contracts | `src/chirp/http/AGENTS.md` |
| Routing and path resolution | `src/chirp/routing/AGENTS.md` |
| Request handling, negotiation, debug, sync path | `src/chirp/server/AGENTS.md` |
| Templates, return types, render plans, OOB, Suspense | `src/chirp/templating/AGENTS.md` |
| Startup contract checks | `src/chirp/contracts/AGENTS.md` |
| Filesystem pages, shells, sections, reactive pages | `src/chirp/pages/AGENTS.md` |
| Middleware and request pipeline safety | `src/chirp/middleware/AGENTS.md` |
| Security primitives | `src/chirp/security/AGENTS.md` |
| Cache backends and cache middleware | `src/chirp/cache/AGENTS.md` |
| Data, schema, migrations, query helpers | `src/chirp/data/AGENTS.md` |
| SSE and reactive events | `src/chirp/realtime/AGENTS.md` |
| MCP/tools integration | `src/chirp/tools/AGENTS.md` |
| CLI and scaffolds | `src/chirp/cli/AGENTS.md` |
| Test helpers | `src/chirp/testing/AGENTS.md` |
| Test suite ownership | `tests/AGENTS.md` |
| Contract test suite ownership | `tests/contracts/AGENTS.md` |
| Examples as executable docs | `examples/AGENTS.md` |
| Narrative docs and release policy | `docs/AGENTS.md` |
| Bengal docs site content/config | `site/AGENTS.md` |
| Benchmarks and performance claims | `benchmarks/AGENTS.md` |

### "ask stewards" workflow

When the user says **"ask stewards"**, run a steward consultation before prioritizing or making
cross-cutting implementation choices.

1. Verify the checkout/ref is current enough for the question: run `git status --short --branch`;
   if network is available and freshness matters, compare with upstream (`git fetch`, then inspect
   branch/ahead-behind). Record any inability to verify freshness.
2. Enumerate steward files with `find . -name AGENTS.md -not -path './.git/*' | sort`.
3. For implementation work, consult the root file plus stewards for the files/subtrees likely to
   change. For backlog, roadmap, or prioritization work, consult all stewards.
4. Ask each steward lens for: top priority, confidence, evidence, dependencies, risks, tempting
   "not now" items, and upstream/downstream service opportunities.
5. Synthesize with weighted voting. Give more weight to convergence, blast radius, dependency
   order, public contract risk, user-visible correctness, risk reduction, and reversibility.
6. Preserve minority reports when a steward has a credible dissent, especially around public API,
   render pipeline, contract severity, free-threading, or performance claims.
7. Produce a short rollup report: recommendation, top 3 priorities, evidence, risks, dependencies,
   minority reports, and "not now" list.

For PRs that used this workflow, add **Steward Notes** with the consulted steward files, the chosen
priority order, and any dissent that reviewers should see.

---

## Anti-patterns

Things that look reasonable and are wrong here:

- **Adding a `to_json()` / `make_response()` / API serialization layer** "for the JSON case." Chirp is not a REST framework. If you genuinely need JSON, use FastAPI for that route. Don't bolt a parallel response model onto Chirp.
- **`{% if key %}` for Suspense deferred values.** Empty list, empty string, 0 — all falsy after resolution. Use `{% if key is not none %}` or `"key" in __chirp_defer_pending__`. The bug only surfaces with realistic data; tests with stub values miss it. Enforced at startup by `app.check()` (category `defer_falsy`, WARNING) when the template self-declares the defer key via `__chirp_defer_pending__` membership or `is deferred`; promote to ERROR in CI via `app.override_contract_severity("defer_falsy", Severity.ERROR)`.
- **Bare jsDelivr URLs for Alpine or plugins.** `https://cdn.jsdelivr.net/npm/alpinejs@3.15.8` resolves to CommonJS, throws a silent `ReferenceError`, and CORS masks it as `"Script error."` Use explicit `/dist/cdn.min.js`. Enforced at startup by `app.check()` (category `alpine_cdn_url`, ERROR) and by `tests/test_alpine.py::test_no_bare_package_urls`; don't disable either.
- **`optional=True` on an OOB region to silence a `BlockNotFoundError`.** That's papering over a typo. `optional=True` is for regions legitimately absent from some layouts (apps without `chirp-ui`). If the block should be there, fix the layout.
- **`try: ... except Exception: pass`.** Ruff S110 catches some; the rest is on you. If you must swallow, log what and why in one line. Per-event SSE error boundaries are *not* this — they're explicit, scoped, and tested.
- **`# type: ignore`** without a comment explaining why. Target is zero. Narrow the type or fix the code.
- **Speculative config options** for "future flexibility." If no one's asking for it, don't add it. The `AppConfig` surface is already wide.
- **Defensive validation inside internal code.** Validate at the boundary (request parsing, form binding, registry registration). Internal code trusts its callers — that's why frozen dataclasses exist.
- **Adding `extends` to a page template** so it can override layout blocks. The composition model is intentional. If you need to inject into the head or scripts region, use the layout's existing extension points or propose a new region. Enforced at startup by `app.check()` (category `composition_extends`, WARNING) when a page-leaf template extends a layout that is registered in this app's chain — block overrides are silently lost AND the layout structure renders twice. Promote to ERROR in CI via `app.override_contract_severity("composition_extends", Severity.ERROR)`. Extending a non-registered kida partial (see `examples/standalone/oob_layout_chain/`) is intentionally allowed.
- **Mutating a registry after freeze.** Registries are intentionally locked at startup so `app.check()` can validate them. Runtime registration is a lifecycle bug waiting to happen.
- **Refactoring during a bug fix.** Separate PR. Exception: the refactor *is* the fix.
- **Adding a parens to a 3.14 multi-exception except.** `except ValueError, TypeError:` is canonical 3.14+ syntax. Ruff normalizes to no-parens. Don't "fix" it.

---

## Done criteria

A change is done when all of these hold:

- [ ] `uv run ruff check .` and `uv run ruff format . --check` clean. No new `# type: ignore` or `# noqa: S110`.
- [ ] `uv run pytest` passes. Coverage stays ≥ 80%.
- [ ] If you touched the hypermedia surface (return types, OOB, Suspense, SSE, fragment dispatch): there's a contract test in `tests/contracts/` exercising the public path end-to-end via `TestClient`. Unit tests are not enough.
- [ ] Tests exercise the *interesting* path: htmx vs non-htmx for `Page`, missing block for OOB, awaitable vs sync context value for Suspense, malformed form for `ValidationError`.
- [ ] If you added a new way to render or wire HTML: there's an `app.check()` rule that catches the wrong way. Contracts beat docs.
- [ ] Free-threading-sensitive change? Note in the PR what shared mutable state you touched and how it's protected (or why it doesn't need to be).
- [ ] Public API changed → CHANGELOG fragment via towncrier (`changelog.d/`, see `changelog.d/README.md` for format — **no leading `-`**), migration note if breaking.
- [ ] Error messages tell the reader what to do next: which template, which block, which registration, what config flag. `BlockNotFoundError`'s message is the bar.
- [ ] PR description explains *why*. The diff explains *what*.

"Tests pass" is not "done." Tests pass on broken hypermedia all the time — the contract is what catches it.

---

## Review and assimilation

- **I read diff-first, description-second.** Tight diff + clear why merges fast; sprawling diff gets questions.
- **One concern per PR.** If the diff needs section headers, it's two PRs. Exception: refactors renaming a concept across many files — one bundled PR beats review churn (e.g. the OOB fail-loud sweep).
- **Commit style:** see `git log`. `feat:` / `fix:` / `refactor:` / `build:` / `deps:` prefixes, imperative, body = motivation. Not enforced — PR title quality matters more than commit prefix.
- **Don't trailing-summary me.** If the diff is readable, I can read it.
- **Flag surprises.** Weird test, unused config, dead-looking code path, an example that does something none of the others do — put it in the PR description. Don't fix silently, don't ignore.
- **Examples are documentation.** If you change a return type or a config field, check whether `examples/` needs updating. A broken example is a broken doc.

---

## When this file is wrong

It will be. Tell me. The worst outcome is that it sits here for a year contradicting how the project actually works. Updates to AGENTS.md are a first-class PR — short, focused, and welcome.
