# RFC 016: Enhancement Tiers As Compiled Fallback Contracts

**Status:** Proposed — research decision only; no template syntax or runtime behavior ships with this RFC
**Issue:** [#347](https://github.com/lbliii/chirp/issues/347)
**Parent:** [#335](https://github.com/lbliii/chirp/issues/335)
**Related:** [#152](https://github.com/lbliii/chirp/issues/152), RFC 008, RFC 015
**Created:** 2026-07-08

## 1. Context

Chirp already proves a useful progressive-enhancement floor for mutations:

- `FormAction` / `MutationResult` returns fragments to htmx and a `303`
  redirect to a plain browser;
- `ValidationError` re-renders server HTML with status `422`;
- the `nojs_floor` contract reports a mutating handler whose source appears to
  return only `Fragment` or `OOB`; and
- `examples/standalone/nojs_floor` exercises create, read, update, delete, and
  validation without sending an htmx header.

That is route-level evidence. It does not describe which named block is the
enhanced surface, which block is the unenhanced surface, or whether the two
surfaces preserve the same DOM target and user task. SSE and other post-load
updates therefore remain outside the current no-JavaScript proof.

Issue #347 proposed attaching this relationship to a named template block:

```kida
{% block chart enhanced="sse" fallback="table" %}
```

That spelling is not valid Kida 0.11 syntax. The locked parser accepts a block
name and an optional `if` expression; the frozen Kida `Block` AST has no
enhancement metadata. Chirp must not make the example appear to work through a
source-regex side channel.

This RFC chooses the intended contract model and the upstream boundary. It does
not accept a public template grammar, add a check category, change a severity,
or claim that enhancement tiers work in 0.9.

## 2. Current evidence

| Surface | Current fact | Evidence |
| --- | --- | --- |
| Mutation fallback | Best-effort handler-source heuristic, `INFO` by default and explicitly promotable | `src/chirp/contracts/rules_nojs_floor.py` |
| Contract proof | htmx-only route is reported; `FormAction`, `Page`, `Template`, and redirects suppress the finding | `tests/contracts/test_nojs_floor.py` |
| Runnable floor | Plain requests prove CRUD, `303`, and `422` behavior | `examples/standalone/nojs_floor/` |
| Browser pattern | The suite knows how to create a Playwright context with JavaScript disabled, but the no-JS example has no such browser test | `examples/standalone/webmcp_form/test_browser_smoke.py` |
| Compiled graph | Routes, templates, blocks, targets, and transition edges are immutable internal records | `src/chirp/app/hypermedia_program.py`, RFC 008 |
| Block grammar | Kida 0.11 exposes block name, body, fragment flag, and optional condition, not arbitrary metadata | declared minimum `kida-templates>=0.11.0`, lock resolution 0.11.0, and the tagged [parser](https://github.com/lbliii/kida/blob/v0.11.0/src/kida/parser/blocks/template_structure.py) / [AST](https://github.com/lbliii/kida/blob/v0.11.0/src/kida/nodes/structure.py) |

The no-JS example means #347 must extend existing evidence rather than create a
second competing floor. The internal program means the relationship should
compile once instead of being rediscovered independently by checks, DevTools,
and tests.

## 3. Decision

Enhancement tiers are an **opt-in relationship between two named blocks in one
logical template**:

1. an enhanced fragment block identifies the transport capability it requires;
2. a fallback block is rendered in the full document without that capability;
3. both blocks own the same literal DOM target;
4. the compiler records a resolved enhanced-to-fallback edge; and
5. `app.check()` validates only explicitly declared relationships.

The first implementation should support `htmx` and `sse` capabilities. These
are capability labels, not a claim that one is a universally “higher” tier.
Islands, WebMCP, and future browser APIs require their own proof before joining
the allowlist.

The intended authoring shape is a Kida-native modifier on a fragment block:

```kida
{% block chart_table %}
<section id="sales-chart">
  <table>...</table>
</section>
{% endblock %}

{% fragment chart_live enhancement="sse" fallback="chart_table" %}
<section id="sales-chart">
  <svg aria-label="Live sales chart">...</svg>
</section>
{% endfragment %}
```

This is **proposed grammar**, not valid syntax in the currently supported Kida
release. The exact tokens become public template behavior only after the Kida
release gate and a separate Chirp implementation check-in.

### Why a block modifier

- The relationship belongs to the named render surface, not an arbitrary HTML
  descendant or a Python registry entry.
- Kida can preserve literal metadata in its AST and template introspection.
- Chirp can compile the edge alongside existing block identities.
- A modifier cannot accidentally execute at render time like a wrapper tag.
- The same template remains the source of full-page, fragment, OOB, Suspense,
  and SSE HTML.

### Rejected alternatives

| Alternative | Reason rejected |
| --- | --- |
| `{# chirp:enhancement ... #}` comments | Comments are not a typed AST contract and invite regex parsing. |
| HTML-only `data-chirp-fallback` attributes | They identify DOM elements but cannot reliably identify the owning named render surface. |
| `app.register_enhancement(...)` | It splits template truth into a parallel Python registry and makes copyable markup incomplete. |
| `AppConfig` flags | Enhancement relationships are application structure, not global configuration. |
| A new return type | Existing return types already express render intent; this contract describes reachability and degradation. |
| Automatic declarations on every `hx-*` attribute | That would create noisy findings and silently change existing applications. |

## 4. Compiled model

The implementation should extend the private `HypermediaProgram`, not create a
second scanner-owned graph. Candidate frozen records are:

```python
@dataclass(frozen=True, slots=True)
class EnhancementNode:
    id: str
    template_id: str
    block_id: str
    capability: Literal["htmx", "sse"]
    fallback_block_id: str
    target_id: str
    origin: SourceOrigin


@dataclass(frozen=True, slots=True)
class EnhancementEdge:
    id: str
    enhanced_block_id: str
    fallback_block_id: str
    resolved: bool
    origin: SourceOrigin
```

The names are illustrative internal design, not public API. An implementation
may model the relationship as another `TransitionEdge` kind if that keeps graph
queries simpler. Either representation must remain frozen, deterministic, and
published under the existing freeze lock.

Compilation needs Kida-provided facts for:

- literal capability and fallback block names;
- whether the enhanced surface is fragment-only;
- the logical template and source line;
- literal root IDs for both blocks when statically available; and
- block reachability during full render.

Dynamic target selection cannot be guessed. It needs a validated declaration
or remains outside the first implementation.

## 5. Contract semantics

The proposed category is `enhancement_tier`. It applies only when an author
uses accepted enhancement metadata. Undeclared templates keep their current
behavior and findings.

An implementation proposal should bring these severities back for explicit
maintainer approval:

| Condition | Proposed severity | Reason |
| --- | --- | --- |
| Unknown capability | `ERROR` | The declared contract cannot be interpreted. |
| Missing fallback block | `ERROR` | The author promised a degradation path that does not exist. |
| Fallback is fragment-only or unreachable in full render | `ERROR` | JavaScript-disabled navigation cannot receive it. |
| Enhanced and fallback roots have different literal target IDs | `ERROR` | A swap can update the wrong region or duplicate visible UI. |
| Required htmx/SSE producer or target edge is unresolved | Existing rule severity | The owning rule remains authoritative; this category adds relationship context. |
| Root ID is dynamic and cannot be proven | `WARNING` or explicit declaration required | Static analysis must not claim proof it does not have. |

No severity changes in this RFC. In particular, `nojs_floor` remains `INFO` by
default, and its existing explicit override remains the application-level way
to enforce the mutation floor.

Diagnostics should name the template, enhanced block, fallback block,
capability, target ID, and source line. Missing fallbacks must fail loud; the
runtime must never substitute an empty block or an empty OOB wrapper.

## 6. Capability-specific proof

### 6.1 htmx

An htmx enhancement contract requires:

- a native `href` or form `action`/`method` path for the same user task;
- a full-page response that contains the fallback block;
- an htmx response from the same template that contains the enhanced block;
- existing target/block and full-document-in-fragment checks to pass; and
- mutation handlers to retain `FormAction`/`ValidationError` semantics where
  applicable.

The contract does not require every interaction to use htmx. It verifies only
the explicitly declared boundary.

### 6.2 SSE

An SSE enhancement contract requires:

- meaningful fallback HTML in the initial full document;
- a resolved EventStream/SSE producer and target relationship;
- compatible literal root IDs for fallback and live fragments;
- disconnect/reconnect behavior to preserve the visible fallback until a valid
  update arrives; and
- no assumption that SSE is available to a JavaScript-disabled browser.

The fallback may be a static snapshot or a normal navigable/form-based view. It
does not need to simulate post-load server push.

## 7. Browser and CI proof

Static checks prove wiring, not user behavior. The prototype must add a browser
matrix:

| Mode | Required observation |
| --- | --- |
| JavaScript disabled | Full page shows the fallback and its native task works. |
| JavaScript enabled, enhancement healthy | The enhanced block updates the same target. |
| JavaScript enabled, transport unavailable | Existing fallback remains visible; no blank replacement occurs. |
| Broken fixture | `app.check()` emits the declared `ERROR` before browser execution. |

Use Playwright's `java_script_enabled=False` context, following the existing
WebMCP fallback test pattern. The canonical no-JS CRUD example remains the
mutation proof; the #347 demo should add one htmx or SSE block relationship
rather than duplicate CRUD.

A future coverage counter may report declared, statically validated, and
browser-exercised enhancement relationships. Coverage output cannot infer that
a Playwright test exists merely because a fallback block compiles.

## 8. Kida release gate

Chirp implementation is blocked until a released Kida version provides a
typed, introspectable contract for literal block modifiers. The upstream work
must:

1. parse modifiers on `block` and `fragment` without weakening current block
   name or optional-condition validation;
2. preserve modifiers on the frozen AST;
3. reject duplicate/unknown modifier syntax with source locations;
4. expose metadata through stable analysis or template introspection; and
5. retain render behavior when metadata is absent.

Chirp must then bump its minimum Kida version, add missing-extra/version
guidance where relevant, and prove ordinary block rendering, fragments,
Suspense, OOB discovery, and compiler identities before consuming the metadata.
No private Kida parser import or source-regex compatibility shim is acceptable.

## 9. ChirpUI policy

ChirpUI components do not receive implicit enhancement metadata in the first
increment. Defaults hidden in a component package would make the application
contract depend on installed package version rather than visible template
intent.

After the core contract is stable, ChirpUI may ship opt-in macros that emit
literal metadata and native fallback markup together. Chirp's compiler still
owns validation, and missing `chirp-ui` must remain an actionable optional-extra
condition rather than breaking core imports.

## 10. Delivery sequence

1. **RFC review:** accept or revise this relationship model and proposed
   severity table. No runtime change.
2. **Kida release:** land typed block modifiers and publish a compatible
   release.
3. **Compiler increment:** add immutable enhancement edges and preserve existing
   graph/severity behavior for undeclared templates.
4. **Contract increment:** add declared-only diagnostics with end-to-end
   `tests/contracts/` proof.
5. **Browser proof:** extend a maintained example with JS-disabled, healthy,
   unavailable-transport, and broken-fixture paths.
6. **Documentation:** publish accepted syntax, diagnostics, ChirpUI guidance,
   and changelog only when behavior ships.

Each implementation increment needs the repository's explicit check-in for
template grammar, compiler shape, `app.check()` severity/default behavior, and
Kida minimum-version changes.

## 11. Success criteria mapping

| #347 criterion | RFC disposition |
| --- | --- |
| Syntax: block attributes vs directive | Prefer literal Kida block/fragment modifiers; reject wrapper directives and sidecars. Public grammar awaits Kida release and review. |
| Relationship to #152 | Extend the shipped route-level floor with a block relationship; reuse its example instead of replacing it. |
| Degraded-mode CI | Require Playwright with JavaScript disabled plus unavailable-transport proof. |
| ChirpUI defaults | No implicit defaults in the first increment; opt-in macros may follow. |
| Missing fallback becomes `ERROR` | Proposed only for an explicit declaration; requires implementation severity approval. |
| Runnable JS-disabled demo | Future implementation deliverable, not claimed by this RFC. |

## 12. Non-goals

- Shipping a runtime feature-detection or polyfill framework.
- Guaranteeing every application works without JavaScript when it has made no
  enhancement declaration.
- Creating a parallel partials directory or alternate serialization path.
- Promoting `nojs_floor` globally from `INFO`.
- Changing render-plan, OOB, Suspense, or block-not-found behavior in this RFC.
- Treating an RFC example as valid copyable syntax before the Kida gate lands.

## 13. Status and collateral

This document is a proposed design and source audit. It changes no public API,
template grammar, CLI, `AppConfig`, return type, contract category, severity,
runtime dependency, example, or generated site output.

No changelog: proposed RFC only; user-visible behavior has not changed.
