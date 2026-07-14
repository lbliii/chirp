# RFC 016: Enhancement Tiers As Compiled Fallback Contracts

**Status:** Accepted in part — Kida 0.12, the private compiler model, and the evidence ledger ship first; diagnostics, runtime behavior, and browser proof remain proposed
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

Issue #347 originally proposed attaching this relationship to a named template
block with an `enhanced=` modifier:

```kida
{% block chart enhanced="sse" fallback="table" %}
```

Kida 0.12 now supports generic typed literal modifiers on blocks and fragments.
Chirp adopts the canonical `enhancement=` spelling, consumes only Kida's public
metadata, and requires `kida-templates>=0.12.0`; it does not use a source-regex
side channel.

This RFC chooses the contract model and records the cleared upstream boundary.
The first Chirp increment accepts the modifier vocabulary and compiles private
facts only. It does not add a check category, change a severity, or alter render
behavior.

## 2. Current evidence

| Surface | Current fact | Evidence |
| --- | --- | --- |
| Mutation fallback | Best-effort handler-source heuristic, `INFO` by default and explicitly promotable | `src/chirp/contracts/rules_nojs_floor.py` |
| Contract proof | htmx-only route is reported; `FormAction`, `Page`, `Template`, and redirects suppress the finding | `tests/contracts/test_nojs_floor.py` |
| Runnable floor | Plain requests prove CRUD, `303`, and `422` behavior | `examples/standalone/nojs_floor/` |
| Browser pattern | The suite knows how to create a Playwright context with JavaScript disabled, but the no-JS example has no such browser test | `examples/standalone/webmcp_form/test_browser_smoke.py` |
| Compiled graph | Routes, templates, blocks, targets, and transition edges are immutable internal records | `src/chirp/app/hypermedia_program.py`, RFC 008 |
| Block grammar | Kida 0.12 exposes ordered literal block/fragment modifiers as immutable, source-located metadata | declared minimum `kida-templates>=0.12.0` and the [Kida 0.12.0 release](https://github.com/lbliii/kida/releases/tag/v0.12.0) |

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

This is the accepted Chirp metadata vocabulary on Kida 0.12. The private
compiler records it now; diagnostics and any runtime behavior still require
separate implementation check-ins.

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
    capability: str | int | float | bool | None
    fallback: str | int | float | bool | None
    fallback_declared: bool
    origin: SourceOrigin


@dataclass(frozen=True, slots=True)
class EnhancementEdge:
    id: str
    enhanced_block_id: str
    fallback_block_id: str
    resolved: bool
    origin: SourceOrigin
```

These are private implementation records, not public API. They remain frozen,
deterministic, and published under the existing freeze lock. Preserving literal
scalar values and whether `fallback=` was present lets the later contract
increment diagnose unknown capabilities, missing fallbacks, and non-string
fallbacks without rescanning template source.

The first compiler increment consumes Kida-provided facts for:

- literal capability and fallback block names;
- the logical template and source line;
- whether a named fallback block resolves in the same logical template.

The contract increment still needs facts for whether the enhanced surface is
fragment-only, literal root IDs when statically available, and full-render
reachability. The compiler does not claim those proofs before the metadata
exists.

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

No severity changes in this compiler increment. In particular, `nojs_floor`
remains `INFO` by default, and its existing explicit override remains the
application-level way to enforce the mutation floor.

Diagnostics should name the template, enhanced block, fallback block,
capability, target ID, and source line. Missing fallbacks must fail loud; the
runtime must never substitute an empty block or an empty OOB wrapper.

### 5.1 Evidence ledger

Issue #723 exercised the frozen compiler facts with intentional declarations,
plain and htmx `TestClient` paths, and undeclared Lucky Cat and Forum Shell
canaries. This is a decision input for the contract increment, not an
`app.check()` behavior or severity change.

| Candidate condition | Observable frozen fact | Evidence disposition | Candidate posture for separate approval |
| --- | --- | --- | --- |
| Accepted `htmx`/`sse` capability with a resolved string fallback | Node preserves the capability and fallback; edge resolves to a block in the same logical template | **Accept as clean** | No finding |
| `fallback=` omitted | `fallback_declared` is false and no edge exists | **Accept** | `ERROR`: the explicit enhancement declaration has no degradation relationship |
| `fallback=` is a non-string literal | Literal value is preserved and no edge exists | **Accept** | `ERROR`: a block identity must be a string |
| String fallback names no block | Edge is preserved with `resolved=False` | **Accept** | `ERROR`: the promised degradation surface does not exist |
| Capability is an unknown string | Literal value is preserved independently of the edge | **Accept** | `ERROR` for the first closed allowlist (`htmx`, `sse`) |
| Capability is a non-string literal | Typed literal is preserved | **Accept** | `ERROR`: a capability identity must be a string |
| Fallback is fragment-only or unreachable in the full render | The current program does not preserve block-vs-fragment kind or full-render reachability | **No-go now** | No diagnostic until the shared compiler can prove the fact |
| Enhanced and fallback literal root IDs differ, or either root is dynamic | The current program does not preserve root-ID evidence | **No-go now** | No diagnostic until source-backed root facts exist |
| Required htmx/SSE producer or target edge is unresolved | Existing rules own those edges and severities; the enhancement node alone does not bind a producer | **Revise** | Add relationship context only after a shared edge can be proved; do not duplicate or promote the owning rule |
| Application has no enhancement declarations | Both canaries compile empty enhancement node/edge tuples | **Accept as clean** | No finding and no implicit ChirpUI defaults |

The false-positive budget is zero false `ERROR`s on the two undeclared
canaries. The known false-negative inventory is explicit: fragment-only/full-
render reachability, root-ID parity, and capability-producer linkage receive no
new finding until the shared compiler can supply those facts.

The five accepted invalid-declaration cases are structurally deterministic and
source-located. Their proposed `ERROR` posture still requires the repository's
explicit severity check-in before implementation. Browser behavior remains a
separate gate: compiler metadata does not prove that a fallback is useful with
JavaScript disabled.

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

## 8. Kida release gate — cleared

Kida 0.12.0 provides the required typed, introspectable contract for literal
block modifiers. The upstream release:

1. parse modifiers on `block` and `fragment` without weakening current block
   name or optional-condition validation;
2. preserve modifiers on the frozen AST;
3. reject duplicate/unknown modifier syntax with source locations;
4. expose metadata through stable analysis or template introspection; and
5. retain render behavior when metadata is absent.

Chirp now requires `kida-templates>=0.12.0`, consumes the public metadata, and
proves ordinary rendering plus immutable compiler identities. No private Kida parser import or source-regex compatibility shim is acceptable.

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

1. **RFC review — complete:** relationship model accepted; no runtime change.
2. **Kida release — complete:** typed block modifiers shipped in Kida 0.12.0.
3. **Compiler increment — complete:** immutable enhancement nodes and edges are
   compiled while existing graph, severity, and render behavior remain stable.
4. **Evidence ledger — complete:** classify deterministic malformed
   declarations, preserve declared-only canary silence, and reject checks whose
   facts are not yet in the shared compiler.
5. **Contract increment:** after explicit severity approval, add only accepted
   declared-only diagnostics with end-to-end `tests/contracts/` proof.
6. **Browser proof:** extend a maintained example with JS-disabled, healthy,
   unavailable-transport, and broken-fixture paths.
7. **Documentation:** publish accepted syntax, diagnostics, ChirpUI guidance,
   and changelog only when behavior ships.

Each implementation increment needs the repository's explicit check-in for
template grammar, compiler shape, `app.check()` severity/default behavior, and
Kida minimum-version changes.

## 11. Success criteria mapping

| #347 criterion | RFC disposition |
| --- | --- |
| Syntax: block attributes vs directive | Use literal Kida block/fragment modifiers with canonical `enhancement=` and `fallback=` names; reject wrapper directives and sidecars. |
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
- Changing render-plan, OOB, Suspense, or block-not-found behavior in this increment.
- Treating compiled metadata as proof that the later diagnostic or browser gates passed.

## 13. Status and collateral

The accepted compiler increment changes the Kida dependency floor and compiles
private enhancement facts. The evidence increment adds fixtures, canary
assertions, and the decision ledger without changing exported Python API, CLI,
`AppConfig`, return types, contract categories, severities, rendering, or
generated site output. A changelog fragment records the dependency and authoring impact;
the evidence-only increment needs no changelog.
