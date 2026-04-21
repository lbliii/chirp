# Epic: `fragment_only` Blocks + SSE Event Default — "One Template, Many Modes" Without the Footguns

**Status**: Draft
**Created**: 2026-04-20
**Target**: next chirp minor (breaking)
**Estimated Effort**: 20–28h
**Dependencies**: `kida-templates >= 0.6.0` (Extension API)
**Source**: Field report from PR #98 (`examples/standalone/returns_gallery`) — real-browser testing surfaced two traps every chirp user hits. See `/tmp/attachments/pasted_text_2026-04-20_17-59-46.txt`.

---

## Why This Matters

Chirp's headline story is "one template, many modes" — a single block serves as a page region, an htmx swap target, an SSE payload, and a Suspense deferred slot. Today that story costs every user two pieces of tribal knowledge, and the failure modes are silent:

1. **SSE events default to `event: fragment`**, not the htmx-default `message`. Users copying a stock htmx-sse snippet get a "Connecting…" spinner forever: the stream connects, bytes arrive, nothing swaps, nothing logs. Found in `src/chirp/realtime/sse.py:279` (`event_name = value.target or "fragment"`).
2. **Blocks intended only as swap targets still render into full pages.** The gallery has three such blocks (`demo_form_ok`, `demo_sse_item`, `demo_mutation_counter`) that leak stale/empty-state content on first paint. Workaround: wrap every body in `{% if trigger_var is defined %}`. Every chirp example has to remember this.

Both have the same root cause: chirp hasn't given the user a vocabulary to say "this block is only a swap target." The workarounds substitute for a missing language feature.

### Consequences

1. **10 examples** use `sse-swap="fragment"` as framework-specific magic (`standalone/returns_gallery`, `standalone/kanban`, `standalone/ollama`, `standalone/sse`, `standalone/chat`, `standalone/hackernews`, `standalone/tools`, `chirpui/kanban_shell`, `chirpui/llm_playground`, plus kanban_shell test).
2. **3 blocks** in `returns_gallery/templates/gallery.html` carry `{% if ... is defined %}` defensive guards that have nothing to do with the block's purpose.
3. **Silent failure modes**: stale DOM content on initial load, or a spinner that never completes — neither produces a log line, a console error, or a contract-check issue.
4. **Onboarding tax**: a net-new chirp user hits both traps inside their first demo and attributes the weirdness to their own code.
5. **Tutorial friction**: every doc page showing SSE must explain "use `sse-swap='fragment'` (that's a chirp thing)" instead of "use htmx as the htmx docs show."
6. **Existing contract check is passive**: `check_sse_event_crossref` (`src/chirp/contracts/rules_sse.py:88-157`) already cross-references `sse-swap` values against `SSEContract.event_types` — but only fires when the route *declares* an `SSEContract`. Undeclared routes (the common case) get no check.

### Fix (one sentence)

Flip the SSE default to unnamed events so htmx's `sse-swap="message"` just works; add a `{% fragment_only %}` kida directive so swap-only blocks can declare that intent; and pair both with a startup contract check that infers emitted event names from route source and fail-louds on any `sse-swap="X"` with no matching emitter.

### Evidence Table

| Source | Key finding | Proposal impact |
|---|---|---|
| `src/chirp/realtime/sse.py:279` — `event_name = value.target or "fragment"` | Default SSE event name is framework-specific, clashes with htmx default | **FIXES** (Sprint 1: drop the fallback) |
| `examples/standalone/returns_gallery/templates/gallery.html:123` + 3× `{% if defined %}` guards | Every example ships the workaround for swap-only blocks | **FIXES** (Sprint 3: `{% fragment_only %}`; Sprint 4: gallery refactor) |
| `src/chirp/contracts/rules_sse.py:88-157` — `check_sse_event_crossref` only crossrefs when `SSEContract.event_types` is declared | No contract safety net for the common case (undeclared SSE routes) | **FIXES** (Sprint 2: extend with source-inferred event names, WARNING → ERROR on typo) |
| `rg 'sse-swap="fragment"'` finds 17 files across examples, tests, docs | Migration surface is bounded and mechanical | **FIXES** (Sprint 1 touches all; Sprint 5 verifies) |
| Kida 0.6.0 ships `Extension` API with `tags`, `parse()`, `compile()` (`site-packages/kida/extensions.py`) | Directive can ship in-repo as a chirp kida-extension, no upstream coordination | **FIXES** (Sprint 0 validates; Sprint 3 implements) |

### Invariants

These must remain true throughout or we stop and reassess:

1. **Named-channel API unchanged**: `SSEEvent(data=..., event="name")` still emits `event: name`. Multiplexing keeps working for reactive/OOB routes; only the default for yielded `Fragment` changes.
2. **OOB fail-loud policy composes**: `fragment_only` blocks must raise `BlockNotFoundError` on missing targets exactly like `{% block %}`. No new silent-failure path.
3. **Zero false positives on the new contract check**: routes whose event names can't be inferred statically (e.g., dynamic `event=variable`) must skip silently, not ERROR. False alarms would train users to add `skip_contract_checks=True` and undo all safety.
4. **Full-template render of a `fragment_only` block produces no output and no side effects** — no trailing whitespace, no invisible wrappers. Whitespace test is a first-class acceptance criterion.

---

## Target Architecture

### SSE serialization (after)

```python
# src/chirp/realtime/sse.py — _format_event()
if isinstance(value, Fragment):
    html = render_fragment(kida_env, value).strip()
    event_name = value.target          # ← was: value.target or "fragment"
    event = SSEEvent(data=html, event=event_name)
    return event.encode()
```

- `yield Fragment("tpl.html", "block")` → SSE frame with no `event:` line → htmx `sse-swap="message"` (default) matches it.
- `yield Fragment("tpl.html", "block", target="feed")` → `event: feed` → `sse-swap="feed"` matches (OOB-to-SSE bridge unchanged).
- `yield SSEEvent(data=html, event="foo")` → `event: foo` (unchanged).

### Kida extension (new)

```python
# src/chirp/templating/kida_fragment_only.py
@dataclass(frozen=True, slots=True)
class FragmentOnlyNode(Node):
    name: str       # block name
    body: list[Node]

class FragmentOnlyExtension(Extension):
    tags = {"fragment_only"}
    end_keywords = {"endfragment_only"}

    def parse(self, parser, tag_name): ...
    def compile(self, compiler, node): ...
```

Two behaviors:
- **Registered as a named block** in the Environment's block table, so `env.get_template(tpl).blocks["x"]` resolves and `render_block("x", ctx)` works. `Fragment("tpl.html", "x", ...)` keeps its current codepath.
- **Suppressed during whole-template render**: the compiled code emits a no-op when the enclosing template is rendered as the root. Detection strategy validated in Sprint 0 (likely: render-context flag set by `render_fragment`, checked by the extension's compiled node).

### Contract check (extended)

```python
# src/chirp/contracts/rules_sse.py
def check_sse_event_crossref(template_sources, router):
    sse_routes = _collect_declared(router)          # current behavior
    sse_routes.update(_infer_from_source(router))   # NEW: scan route source
    # crossref swap_values against declared ∪ inferred
```

Inference regex scans each SSE route handler's source for:
- `yield SSEEvent(..., event="name")` — literal string
- `yield Fragment(..., target="name")` — literal string
- Skips any route where either call uses a non-literal `event=`/`target=` (can't prove negative).

Issues upgraded from WARNING to ERROR for undeclared misses (an event name that appears in `sse-swap=` but in no emitter source) — this is a post-flip reality check.

---

## Sprint Structure

| Sprint | Focus | Effort | Risk | Ships Independently? |
|---|---|---|---|---|
| 0 | Design & Validate (kida detection mechanism, inference regex, migration matrix) | 3–4h | Low | Yes (RFC only) |
| 1 | SSE default flip + mechanical example/test/doc migration | 4–6h | Medium (breaking) | Yes |
| 2 | SSE contract check: source-inferred event names | 3–4h | Low | Yes |
| 3 | `{% fragment_only %}` kida extension + tests | 5–7h | Medium (kida API surface) | Yes |
| 4 | Gallery refactor + `docs/guides/fragment-blocks.md` + towncrier roll-up | 3–4h | Low | Yes |
| 5 | Audit other examples for fragment-only candidates; browser smoke test | 2–3h | Low | Yes |

Each sprint produces a reviewable, standalone PR. Sprints 1–2 can land before 3 (they don't depend on the directive); Sprints 4–5 require 1+3.

---

## Sprint 0: Design & Validate

**Goal**: Solve the two hard design questions on paper before writing extension code.

### Task 0.1 — Validate kida block-vs-root detection

Confirm how `FragmentOnlyExtension` detects whether it's rendering as the root template vs as a named block target.

- Read `src/chirp/templating/integration.py` `render_fragment()` and the kida call path
- Check whether `RenderContext` exposes a "rendering named block" flag, or if we need to set a context variable at the `render_fragment` entry point
- Alternative: compile the fragment_only body into the block table only (no emit call in the root template's code path)

**Files**: `src/chirp/templating/integration.py`, `site-packages/kida/render_context.py`, `site-packages/kida/compiler/`
**Acceptance**: Short design note in this doc appending to §Target Architecture picking one of {context-flag, compiler-level suppression, hybrid}. Include the 3-line sketch that would work.

### Task 0.2 — SSE event-name inference regex

Draft the regex for detecting `yield SSEEvent(..., event="X")` and `yield Fragment(..., target="X")` in route source.

- Reuse the approach from `src/chirp/contracts/checker.py:79-82` (template-call regex)
- Must handle: positional and keyword args, single and double quotes, line continuations
- Must safely skip: `event=variable`, `event=f"..."`, `event=CONST` (anything non-literal)

**Acceptance**: regex + 8 test cases (positive: 4; negative-skip: 4) listed in the design note. Negative cases must not be flagged as "can match."

### Task 0.3 — Migration matrix

For each of the 17 files that reference `sse-swap="fragment"`, classify:
- (a) Remove attribute (unnamed event, htmx default) — the recommended path
- (b) Keep explicit, migrate emitter to `SSEEvent(event="fragment")` — only if a template reader benefits from the explicit name
- (c) Block-is-also-fragment-only (needs Sprint 3 work too)

**Acceptance**: 17-row table in this doc with column `Migration` ∈ {(a), (b), (c)}, and file+line for each.

### Task 0.4 — Breaking-change audience sizing

Grep the open-source world if feasible, but at minimum count: how many chirp apps in this repo's examples + chirpui examples rely on the default? Any downstream packages that import `chirp`?

**Acceptance**: 1-paragraph note establishing scope. If external downstream users exist, towncrier entry in Sprint 1 must include the named migration SQL recipe.

---

## Sprint 1: SSE Default Flip

**Goal**: Change default from `event: fragment` to unnamed, migrate every consumer in-repo.

### Task 1.1 — Flip the default

- `src/chirp/realtime/sse.py:279`: `event_name = value.target` (drop `or "fragment"`)
- Update `_format_event` docstring (line 260): remove "wrap with event: fragment" language; replace with "emit unnamed SSE event (htmx `sse-swap='message'` default) unless the Fragment has an OOB target."
- Update `EventStream` docstring (`src/chirp/realtime/events.py:43`): same.

**Files**: `src/chirp/realtime/sse.py`, `src/chirp/realtime/events.py`
**Acceptance**: `rg '"fragment"' src/chirp/realtime/ → zero hits` except in the testing module that inspects wire format for old apps (if any — verify).

### Task 1.2 — Migrate examples

Per Sprint 0.3 migration matrix, update each example template. For migration (a), drop `sse-swap="fragment"` (htmx default kicks in). Also drop `hx-ext="sse"` if it was added solely for `sse-swap` (keep if `sse-connect` is on a parent).

**Files** (from `rg 'sse-swap="fragment"' examples/`):
- `examples/standalone/returns_gallery/templates/gallery.html:123`
- `examples/standalone/kanban/templates/board.html:187`
- `examples/standalone/ollama/templates/chat.html:289,322`
- `examples/standalone/sse/templates/feed.html:29`
- `examples/standalone/chat/templates/chat.html:77`
- `examples/standalone/hackernews/README.md:81`
- `examples/standalone/tools/templates/notes.html:134`
- `examples/chirpui/kanban_shell/pages/page.html:227` + `test_app.py:503`
- `examples/chirpui/llm_playground/templates/playground.html:23,42`

**Acceptance**: `rg 'sse-swap="fragment"' examples/ → zero hits`. Start each example's server, open in a browser, confirm live updates still swap.

### Task 1.3 — Migrate tests

- `tests/test_sse_macros.py`, `tests/contracts/test_swap.py`, `tests/contracts/test_sse.py`: update any assertion that expects `event: fragment` in the wire output. Add an explicit test: `yield Fragment(...)` without target produces a frame with no `event:` line.
- `tests/templates/boundary/chirpui_index.html`: migrate or delete if stale.

**Acceptance**: `uv run pytest tests/test_sse_macros.py tests/contracts/` green. New test `test_yielded_fragment_emits_unnamed_event` present.

### Task 1.4 — Migrate docs

- `site/content/docs/streaming/sse-patterns.md`
- `site/content/docs/tutorials/view-transitions-oob.md`
- `site/content/docs/guides/app-shell.md`

Replace `sse-swap="fragment"` with either no attribute (most cases) or the explicit named-channel form.

**Acceptance**: `rg 'sse-swap="fragment"' site/ → zero hits`. Prose updated where it previously explained the chirp-specific default.

### Task 1.5 — Towncrier entry

`changelog.d/+sse-event-default.changed.md`:

> **Breaking**: `EventStream` now emits yielded `Fragment`s as unnamed SSE events (htmx default `sse-swap="message"` matches). Previously the default event name was `fragment`. Apps using `sse-swap="fragment"` must either remove the attribute (recommended) or switch the emitter to `yield SSEEvent(data=frag, event="fragment")` for explicit named-channel semantics. The contract check added in this release will flag the mismatch at startup.

**Acceptance**: file present; `uv run towncrier build --draft --version=…` renders correctly.

---

## Sprint 2: SSE Contract Check — Source-Inferred Event Names

**Goal**: Startup ERROR when `sse-swap="X"` references an event name that no emitter in the connected route produces.

### Task 2.1 — Source inference helper

Add `_infer_emitted_events(router)` in `src/chirp/contracts/rules_sse.py` using the Sprint 0.2 regex.

- Iterate `router.routes`, open each handler's source (`inspect.getsource`)
- Collect literal `event=`/`target=` strings from `yield SSEEvent(...)` and `yield Fragment(...)` calls
- Return `dict[path, set[str] | None]` (None = can't prove negative → skip route in crossref)

**Files**: `src/chirp/contracts/rules_sse.py`, `src/chirp/contracts/patterns.py` (regex constant)
**Acceptance**: unit test with 8 inputs from Sprint 0.2 matrix.

### Task 2.2 — Extend `check_sse_event_crossref`

Merge inferred events with `SSEContract.event_types`. Issue severity rules:
- `sse-swap="X"` + neither declared nor inferred for connected route → **ERROR** (was WARNING when declared-only)
- `sse-swap="X"` + inference=None (can't prove) + no declaration → **INFO** (skipped, noted for debug)
- Declared event not listened to → keep INFO (current behavior)

**Files**: `src/chirp/contracts/rules_sse.py:88-157`
**Acceptance**: `uv run pytest tests/contracts/test_sse.py` green. New test `test_crossref_catches_bad_swap_against_inferred` passes.

### Task 2.3 — Integration test: break returns_gallery, confirm startup ERROR

Script: copy returns_gallery, change `sse-swap="task_count"` to `sse-swap="foo"`, run `app.check()`, assert ERROR issue with category `sse_crossref` naming `foo` and the matched route.

**Files**: `tests/contracts/test_sse.py`
**Acceptance**: the negative test passes after the check is extended.

### Task 2.4 — Towncrier entry

`changelog.d/+sse-crossref-inference.added.md`: "Contract check now infers SSE event names from route source (yielded `SSEEvent`/`Fragment`) and fail-louds at startup when `sse-swap="X"` references an event no route emits."

---

## Sprint 3: `{% fragment_only %}` Kida Extension

**Goal**: New directive that defines a named block whose body renders only when invoked as a render target, not during full-template renders.

### Task 3.1 — Implement `FragmentOnlyExtension`

- New file `src/chirp/templating/kida_fragment_only.py`
- Subclass `kida.extensions.Extension`
- `tags = {"fragment_only"}`, `end_keywords = {"endfragment_only"}`
- `parse()`: consume tag, parse block name, parse body until `endfragment_only`, return `FragmentOnlyNode(name, body)`
- Register the name in the template's block table so `render_block("name", ctx)` finds it
- `compile()`: per Sprint 0.1 decision, compile the body either behind a render-context flag check or only into the block registration (not the root render path)

**Files**: `src/chirp/templating/kida_fragment_only.py` (new); `src/chirp/templating/integration.py:158` (register in `Environment(extensions=[FragmentOnlyExtension, ...])`)
**Acceptance**: `{% fragment_only x %}HELLO{% endfragment_only %}` in `t.html`:
- `env.get_template("t.html").render(ctx)` produces `""` (no `HELLO`, no whitespace)
- `render_block("t.html", "x", ctx)` produces `"HELLO"`

### Task 3.2 — OOB fail-loud parity

Ensure a `{% fragment_only %}` block registered as an OOB region raises `BlockNotFoundError` on missing targets, just like `{% block %}`. Also verify `app.check()` `oob_registry` category treats it identically.

**Files**: `src/chirp/errors.py`, `src/chirp/contracts/rules_fragment_targets.py`
**Acceptance**: test `test_fragment_only_oob_fail_loud` passes.

### Task 3.3 — Whitespace contract

Add a unit test asserting a `fragment_only` block emits zero characters during full-template render — no trailing newline, no leading whitespace. This is the silent-failure guardrail (Invariant 4).

**Files**: `tests/templating/test_fragment_only.py` (new)
**Acceptance**: `assert output == ""` (not `.strip() == ""`).

### Task 3.4 — Interaction with `Suspense` deferred blocks

Confirm `Suspense` still works correctly when a deferred slot uses `{% block %}` (current path). Document explicitly in Sprint 4 guide that `Suspense` uses `{% block %}` + `is deferred` check, not `{% fragment_only %}` — because the shell must render a placeholder.

**Files**: (docs only in Sprint 4)
**Acceptance**: `tests/test_suspense.py` regression tests green. Note in guide.

### Task 3.5 — Towncrier entry

`changelog.d/+fragment-only-directive.added.md`: "New `{% fragment_only %}` kida directive for blocks that only render as swap targets. Body is suppressed during full-template renders; block registers normally for `Fragment("tpl.html", "name", ...)`."

---

## Sprint 4: Gallery Refactor + Docs

**Goal**: Reference-design consumer of `fragment_only`; codify the "one template, many modes" vocabulary.

### Task 4.1 — Gallery refactor

Replace the three `{% if ... is defined %}` guards in `examples/standalone/returns_gallery/templates/gallery.html` with `{% fragment_only %}`. Blocks: `demo_form_ok`, `demo_sse_item`, `demo_mutation_counter` (verify via read — brief lists two definitively, a third was added as an SSE payload target).

**Files**: `examples/standalone/returns_gallery/templates/gallery.html`, `examples/standalone/returns_gallery/README.md`
**Acceptance**: browser smoke test per "Verification" below. `rg '{% if .* is defined %}' examples/standalone/returns_gallery/ → zero hits`.

### Task 4.2 — `docs/guides/fragment-blocks.md`

New guide under `site/content/docs/guides/fragment-blocks.md` covering:
- When to use `{% block %}` (renders in-page AND as swap target, e.g., a form)
- When to use `{% fragment_only %}` (renders ONLY as swap target, e.g., success state, SSE payload)
- Interaction with `Suspense` (still `{% block %}` + `is deferred`, not `fragment_only`; call it out explicitly)
- Migration recipe for apps currently using `{% block %}` + `{% if defined %}` workaround

**Files**: `site/content/docs/guides/fragment-blocks.md` (new)
**Acceptance**: guide passes the site-build (`uv run site-build` or equivalent); reviewer read-through catches no gaps.

### Task 4.3 — Gallery README decision-table cross-link

Cross-link the new guide from the gallery README and the README's SSE decision table.

**Files**: `examples/standalone/returns_gallery/README.md`, root `README.md` if it has a gallery link.

---

## Sprint 5: Broader Example Audit + Browser Smoke

**Goal**: Find the other examples where `{% block %}` is actually fragment-only and migrate them.

### Task 5.1 — Audit

For each example that uses htmx swap targets, grep for `{% if .* is defined %}` and for blocks whose names appear in `Fragment("...", "name", ...)` calls but never in `Template("...", ...)`. Classify.

**Acceptance**: short audit matrix in a PR comment (or appended to this plan); migrate the obvious cases (kanban, hackernews, chat likely qualify).

### Task 5.2 — Browser smoke matrix

Start each migrated example, open in a real browser (not curl/WebFetch — PR #98 proved curl misses this class of bug), walk the golden paths:
- returns_gallery (full matrix)
- sse (feed updates)
- kanban (live board)
- hackernews (stream)
- chat (message stream)

**Acceptance**: each walks green. Screenshot or terminal transcript attached to PR.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Kida Extension API can't detect root-vs-block render | Medium | High (blocks Sprint 3) | Sprint 0.1 validates on paper first; fallback = upstream a tiny patch to kida (flag in `RenderContext`). Owner is same (you). |
| Inference regex produces false positives, users disable contract checks | Low | High (undoes safety for everyone) | Sprint 0.2 negative-case matrix; inference=None path returns INFO not ERROR. Invariant 3. |
| Downstream apps break on SSE flip without warning | Medium | Medium | Sprint 2 contract check flags the mismatch at startup — users see the issue before their browser does. Towncrier entry includes explicit migration recipe. |
| `fragment_only` full-template emits invisible whitespace | Low | Medium (silent DOM noise) | Sprint 3.3 whitespace contract is an explicit `assert output == ""` test, not `.strip()`. |
| `Suspense` regresses because someone naively converts a block to `fragment_only` | Medium | Medium | Guide explicitly warns; add a contract-check rule "Suspense deferred context key X maps to a `fragment_only` block" → ERROR. (Deferred to Sprint 3.4 if needed.) |
| SSE error renderer (`_format_error_event`) still sends `event: fragment` literal | Low | Low | Sprint 1.1 audit — `sse.py:318-320` emits to `value.target`, no literal "fragment"; verify no other literal remains. |

---

## Success Metrics

| Metric | Current | After Sprint 2 | After Sprint 3 | After Sprint 5 |
|---|---|---|---|---|
| `sse-swap="fragment"` in repo (examples + tests + docs) | 17 files | 0 files | 0 files | 0 files |
| `{% if … is defined %}` guards in `returns_gallery` | 3 | 3 | 3 | 0 |
| `{% if … is defined %}` guards across all examples (as fragment-only workaround) | unknown (audit in 5.1) | unknown | unknown | 0 |
| Contract check catches bad `sse-swap="foo"` at startup | No | Yes, ERROR | Yes, ERROR | Yes, ERROR |
| `docs/guides/fragment-blocks.md` exists | No | No | No | Yes |
| `yield Fragment(...)` without target → htmx-default `message` works in a stock snippet | No | — | — | Yes (verified in browser) |

---

## Relationship to Existing Work

- **PR #98 (`examples/standalone/returns_gallery`)** — prerequisite; this epic is the proper-fix follow-through on two workarounds shipped there. Gallery refactor (Sprint 4.1) reverts those workarounds.
- **`plan/completed/rfc-sse-scope-stability.md`** — parallel SSE hardening work; this epic does not touch scope stability but shares the same subsystem. Review its invariants before Sprint 2.
- **OOB registry fail-loud (`docs/guides/oob-registry.md`, merged)** — Sprint 3.2 `fragment_only` must compose with this, not bypass it.
- **Not in scope** (per brief):
  - Devtools errors-tab auto-population (`src/chirp/server/devtools/js/ui.js:414-423`) — separate UX polish epic.
  - `ValidationError` client-side auto-swap (chirp-injected `htmx.config.responseHandling`) — related but separate PR.
  - Stream vs Suspense docs — already correct in PR #98.

---

---

## Sprint 0 Design Notes

### 0.1 — Kida block-vs-root detection: already solved upstream

**Finding**: Kida 0.6.0 ships `{% fragment name %}...{% end %}` natively. Parser is `kida/parser/blocks/template_structure.py:197` (`_parse_fragment_tag`); compiler is `kida/compiler/statements/template_structure.py:108-110` (`if node.fragment: return []`). Parses to the same `Block` AST node with `fragment=True`, so every existing chirp integration that consumes `block_metadata()` already sees fragment blocks identically.

**Verified at REPL**:
```
{%- fragment only_swap -%}<div>HELLO</div>{%- end -%}
```
- `tpl.render()` → `"BEFOREAFTER\n"` (body fully suppressed, whitespace controlled by `{%- -%}` like any tag)
- `tpl.render_block("only_swap")` → `"<div>HELLO</div>"`
- `tpl.block_metadata()` → `{"only_swap": BlockMetadata(...)}` — fragment blocks ARE in the metadata table

**Implication (big)**: Sprint 3 collapses. **No `FragmentOnlyExtension` needed.** **No chirp kida-integration code.** The directive already exists, we just teach users about it. Sprint 3 becomes:
- Integration smoke tests to confirm OOB registry, `rules_fragment_targets`, `rules_unreachable_blocks`, `rules_page_shell`, Suspense discovery, and `Fragment("tpl.html", "name", ...)` all work identically on `fragment=True` blocks. Expectation: everything already works because the AST shape is unchanged.
- Nothing new to register.

**Naming**: use kida's term. The directive is `{% fragment %}`, not `{% fragment_only %}`. Docs and guide use "fragment block." Epic retitled to drop `_only`.

**Effort revision**: Sprint 3 drops from 5-7h → 1-2h. Total epic: 15-22h (was 20-28h).

---

### 0.2 — SSE event-name inference: use `ast`, not regex

**Decision**: parse handler source with `ast`, walk for `ast.Call` nodes whose func name is `SSEEvent` or `Fragment`, extract `event=`/`target=` kwargs only when the value is `ast.Constant(str)`. This is more reliable than regex and matches how other chirp checks (e.g., `rules_reactive`) already work.

**Sketch**:
```python
import ast, inspect

def _infer_emitted_events(handler) -> set[str] | None:
    """Return event names provably emitted, or None if any call is non-literal."""
    try:
        source = inspect.getsource(handler)
    except (OSError, TypeError):
        return None
    tree = ast.parse(textwrap.dedent(source))
    emitted: set[str] = set()
    confident = True
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func_name = _call_name(node.func)
        if func_name == "SSEEvent":
            kw = _find_kwarg(node, "event")
        elif func_name == "Fragment":
            kw = _find_kwarg(node, "target")
        else:
            continue
        if kw is None:
            continue  # default (None/no event) — fine
        if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            emitted.add(kw.value.value)
        else:
            confident = False  # non-literal; can't prove negative
    return emitted if confident else None
```

**Positive cases** (return `{"X"}`):
1. `yield SSEEvent(data="x", event="ready")` → `{"ready"}`
2. `yield SSEEvent(data, event="ping", id="1")` → `{"ping"}`
3. `yield Fragment("tpl.html", "block", target="hero")` → `{"hero"}`
4. `yield Fragment("tpl.html", "block", ctx, target="feed")` → `{"feed"}`

**Negative-skip cases** (return `None` — inference=unavailable, crossref skips):
1. `yield SSEEvent(data="x", event=variable)` → `None`
2. `yield SSEEvent(data="x", event=f"prefix_{id}")` → `None`
3. `yield Fragment("tpl.html", "block", target=build_target())` → `None`
4. `yield Fragment("tpl.html", "block", target=EVENT_NAME)` → `None` (module-level const; we don't follow)

Invariant 3 (no false positives) is preserved: any unprovable call → `None` → route skipped.

---

### 0.3 — 17-file migration matrix

All 17 references classify as **(a) drop `sse-swap="fragment"` attribute**. One framework macro needs a default change. Specifics:

| # | File | Line(s) | Classify | Notes |
|---|---|---|---|---|
| 1 | `examples/standalone/returns_gallery/templates/gallery.html` | 123 | (a)+(c) | Drop attr; block `demo_sse_item` also migrated to `{% fragment %}` in Sprint 4. |
| 2 | `examples/standalone/kanban/templates/board.html` | 187 | (a) | Hidden sink div; drop attr. |
| 3 | `examples/standalone/ollama/templates/chat.html` | 289 | (a) | |
| 4 | `examples/standalone/ollama/templates/chat.html` | 322 | (a) | |
| 5 | `examples/standalone/sse/templates/feed.html` | 29 | (a) | |
| 6 | `examples/standalone/chat/templates/chat.html` | 77 | (a) | |
| 7 | `examples/standalone/hackernews/README.md` | 81 | (a) | Prose example; drop attr. |
| 8 | `examples/standalone/tools/templates/notes.html` | 134 | (a) | |
| 9 | `examples/chirpui/kanban_shell/pages/page.html` | 227 | (a) | Inside `{# comment #}` — prose update. |
| 10 | `examples/chirpui/kanban_shell/test_app.py` | 503 | (a) | Docstring; update prose. |
| 11 | `examples/chirpui/llm_playground/templates/playground.html` | 23, 42 | (a) | Two occurrences. |
| 12 | **`src/chirp/templating/macros/chirp/sse.html`** | 17 | **(macro change)** | The `sse_scope` macro defaults `swap="fragment"`. Change default to empty/omitted so `{{ sse_scope("/events") }}` renders without `sse-swap=` attribute. Users can still pass `swap="status"` explicitly. **Framework-level change, not just migration.** |
| 13 | `tests/test_sse_macros.py` | 38 | (test update) | Assert macro default produces no `sse-swap` attr; add a test for `swap="status"` explicit. |
| 14 | `tests/contracts/test_swap.py` | 67, 82 | (keep, audit) | Test input exercising swap rules; the literal `"fragment"` is incidental. Keep but confirm assertions still hold post-flip. |
| 15 | `tests/contracts/test_sse.py` | 106, 115, 121 | (keep, audit) | Test input for self-swap crossref rule; same call. Post Sprint 2, add new cases for inference-based ERROR. |
| 16 | `tests/templates/boundary/chirpui_index.html` | - | (a) | Boundary test fixture. If stale, delete. Otherwise drop attr. |
| 17 | `site/content/docs/streaming/sse-patterns.md` `tutorials/view-transitions-oob.md` `guides/app-shell.md` | 145 / 74 / - | (a) | Docs prose; drop attr in examples, update surrounding explanation (no more "chirp uses `event: fragment`"). |

**Key discovery**: the `chirp/sse.html` `sse_scope` macro (item 12) is the *most consequential* single change. Every app using `{{ sse_scope("/events") }}` gets the fix for free after the macro default flips. This moves some acceptance criteria from Sprint 1.2 into Sprint 1.1 (framework change, not migration).

---

### 0.4 — Breaking-change audience

- **PyPI name**: `bengal-chirp`, version `0.4.0` (pyproject.toml). Pre-1.0 — breaking changes are expected and don't warrant an LTS/deprecation cycle.
- **Repo authorship**: single maintainer (`lbliii`); no co-maintainers visible in recent git log.
- **In-repo consumers**: 10 examples + `chirp-ui`'s `chirp_ui.package` (no `sse-swap="fragment"` references in `chirp-ui` itself; verify before Sprint 1).
- **External downstream packages**: unknown. Package is listed on PyPI as early-stage framework; realistic audience = handful of alpha adopters.
- **Migration recipe** (to include in the towncrier entry):
  ```
  # Before
  yield Fragment("tpl.html", "item", item=x)   # → event: fragment
  # in template: <div sse-swap="fragment">

  # After (recommended)
  yield Fragment("tpl.html", "item", item=x)   # → no event name
  # in template: <div> (no sse-swap — htmx default "message" matches)

  # After (explicit, if name is load-bearing)
  yield SSEEvent(data=render_fragment(...), event="fragment")
  # in template: <div sse-swap="fragment">
  ```
- **Signal strength**: the Sprint 2 contract check fires at `app.run()` startup naming the exact attribute. Upgraders who skim release notes will still get an ERROR pointing at the bad HTML. This is the strongest migration affordance possible short of an automated codemod.

**Verdict**: ship as a plain breaking change. Single towncrier entry in Sprint 1.5 with the recipe above. No deprecation cycle needed at v0.4.x. Flag the breaking change prominently in the next release's headline so alpha users see it before the contract check does.

---

## Changelog

| Date | Author | Change |
|---|---|---|
| 2026-04-20 | lbliii (drafted by Claude) | Initial draft from PR #98 field report; evidence gathered from `src/chirp/realtime/sse.py`, `src/chirp/contracts/rules_sse.py`, `src/chirp/templating/integration.py`, kida 0.6.0 `extensions.py`. |
| 2026-04-20 | lbliii (Sprint 0 design pass) | Added Sprint 0 design notes. **Major finding**: kida 0.6.0 ships `{% fragment %}` natively → Sprint 3 collapses to integration smoke tests. AST-based inference design replaces regex approach. Identified framework macro `chirp/sse.html` as highest-leverage single change. Effort revised: 15-22h (was 20-28h). |
