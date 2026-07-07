# RFC 014: Universal Operation Projections

**Status:** Accepted — declarative WebMCP form preview implemented; other projections pending
**Issue:** [#339](https://github.com/lbliii/chirp/issues/339)
**Parent epic:** [#568](https://github.com/lbliii/chirp/issues/568)
**Saga:** [#566](https://github.com/lbliii/chirp/issues/566)
**Created:** 2026-07-06

This RFC decides how one typed Python operation can be projected into browser
HTTP, htmx, a human and programmatic CLI, ordinary MCP tools, WebMCP, and MCP
Apps without giving Chirp a REST serialization layer or giving Milo ownership
of HTML rendering. The declarative WebMCP form slice is now implemented by
issue #574 through an explicit `FormContract` projection. The Milo, ordinary
MCP, and MCP Apps projections remain design-only; this document does not claim
that those pending surfaces ship.

The external evidence used for this decision is pinned to:

- Milo `0.3.1`, commit
  `1f5370861fa38bc7942111a623fa2cb5a7f567b9`;
- the WebMCP proposal, commit
  `0b676d27a08aafd3b4f8a709756eeeab342fd9bd`; and
- Milo's open MCP Apps boundary issue
  [#74](https://github.com/lbliii/milo/issues/74).

Later implementation issues must re-run their compatibility proof against the
version they actually depend on. These pins describe the evidence behind this
RFC, not permanent dependency floors.

## 1. Decision summary

Chirp will provide an **optional, explicit Milo projection adapter**. The
adapter consumes an already registered Milo `CommandDef` and binds selected
web and agent surfaces to it. It does not introduce a second operation
decorator, schema compiler, command registry, renderer, or generic serializer.

1. Milo's dotted command path, such as `work-items.create`, is the stable
   operation identity. Milo owns the callable, input/output schemas, CLI
   invocation, generic MCP tool shape, annotations, and generic result/error
   encoding.
2. Chirp owns routes, requests, server-side authorization, form binding,
   validation display, htmx negotiation, return types, Kida render plans,
   named blocks, and fail-loud HTML behavior.
3. An operation callable accepts typed domain inputs. It does not accept a
   Chirp `Request`, and a web projector does not manufacture a Milo `Context`.
   Surface-specific context stays at the adapter boundary.
4. A web binding explicitly maps a route and form onto an operation and maps
   the typed domain result onto existing Chirp return types. HTML is never
   inferred from `outputSchema` and is never converted through JSON.
5. Every projection is independently opt-in. Registering a Milo command does
   not make it an HTTP route, WebMCP tool, MCP tool, or MCP App. Registering a
   Chirp route does not make it an agent tool.
6. WebMCP's first preview is declarative form enhancement only. The browser
   fills and submits the same real HTML form; Chirp's server remains the
   authority. Mutation forms omit `toolautosubmit`.
7. MCP Apps use a `ui://` resource owned by Milo and HTML rendered by Chirp
   from an explicitly configured named block. A missing required block raises
   `BlockNotFoundError`; an empty fallback is forbidden.
8. The first universal-operation compatibility tier is finite synchronous
   operations. Async operations, cancellation, and cross-surface streaming are
   rejected at registration until Milo and Chirp can prove equivalent
   semantics. Chirp `Stream`, `Suspense`, and `EventStream` remain web-specific
   return types rather than generic operation results.
9. The adapter compiles setup-time declarations into Chirp's existing internal
   `HypermediaProgram`. It does not scan or mutate registrations after freeze.
10. The existing provisional `app.tool()` registry remains supported while a
    separately reviewed migration is developed. This RFC does not silently
    alias or remove it.

## 2. Why this boundary

Chirp's architecture starts with HTML and typed return values. Milo starts with
typed Python callables and projects them into command and MCP protocols. The
overlap is useful, but merging the two runtimes would damage both:

- using a Milo output schema to synthesize web responses would create the
  generic JSON side channel Chirp intentionally avoids;
- teaching Milo about `Page`, `Fragment`, OOB, Suspense, or named blocks would
  move Chirp's render contract into a generic CLI library;
- giving Chirp another annotation-to-schema compiler would duplicate Milo's
  `function_to_schema()` and let the surfaces drift; and
- automatically publishing every command would turn local implementation
  details into remotely invocable authority.

The adapter is therefore a projection boundary, not a shared replacement
runtime. It joins stable identities and typed values while leaving protocol
behavior with the framework that already owns it.

## 3. Authority map

| Concern | Authority | Adapter responsibility |
| --- | --- | --- |
| Callable and typed parameters | Milo `CommandDef.handler` | Resolve one explicit dotted identity |
| Input/output schema | Milo `function_to_schema()` / return schema | Compare web fields; do not rewrite schema |
| CLI parsing, help, exit code, output format | Milo | None |
| Ordinary MCP tool descriptor and generic result | Milo | Select an explicit allowlist |
| HTTP route and request lifecycle | Chirp | Register one normal route per web binding |
| Authentication and authorization | Application through Chirp/Milo middleware | Require a policy for exposed mutations |
| Form decoding and validation display | Chirp/application | Bind request data to typed kwargs |
| HTML and htmx negotiation | Chirp return types and render plan | Project the domain result to an existing return type |
| WebMCP discovery | Browser proposal, emitted by Chirp | Add verified attributes to the same real form |
| MCP App protocol and `ui://` metadata | Milo | Render configured Chirp block for Milo's resource |
| Template/block existence | Chirp compiler and `app.check()` | Declare graph edges and fail loud |
| Generic serialization | Milo | Never add a Chirp serializer |

No adapter may override an authority named in this table to work around a gap.
A missing Milo capability is an upstream dependency or a reduced compatibility
tier, not permission to add `to_json()` to Chirp.

## 4. Proposed public setup surface

The implementation issue may make the following provisional names public only
after the repository's public-API check-in. The shape accepted by this RFC is:

```python
from chirp.ext.milo import MCPAppProjection, WebProjection, use_milo
from milo import CLI

cli = CLI(name="work-items")
work_items = cli.group("work-items")


@work_items.command(
    "create",
    description="Create a work item",
    confirm="Create this work item?",
    annotations={"destructiveHint": False, "idempotentHint": False},
)
def create_work_item(title: str, priority: int = 2) -> WorkItemReceipt:
    return service.create(title=title, priority=priority)


operations = use_milo(app, cli)
operations.bind(
    "work-items.create",
    web=WebProjection(
        path="/work-items",
        methods=("POST",),
        template="work_items.html",
        form_block="create_form",
        result_block="work_item_row",
        bind=bind_create_form,
        render=render_created_work_item,
        authorize=require_editor,
    ),
    mcp=True,
    webmcp=True,
    mcp_app=MCPAppProjection(
        uri="ui://chirp/work-items/create",
        block="create_tool",
    ),
)
```

The exact constructor spelling may be refined during implementation, but these
semantic requirements may not change without amending the RFC:

- `use_milo()` is an optional adapter entry point, not a core `AppConfig`
  field or mandatory import;
- `bind()` names an existing Milo command by dotted path;
- every projection is an explicit keyword with a closed default;
- web route, methods, template, form block, result block, binder, renderer,
  and authorization policy are visible setup-time declarations;
- projection records are frozen and slotted;
- `bind()` is setup-only and rejects use after app freeze; and
- the bridge registers through the existing domain/freeze lifecycle rather
  than adding request-time registry mutation.

`WebProjection.render` receives the typed operation result and returns an
existing Chirp return type, normally `Page`, `Fragment`, `MutationResult`, or
`FormAction`. It may also return an existing `ValidationError` when the
operation defines a domain validation failure. It may not return an invented
JSON envelope.

`WebProjection.bind` owns conversion from `Request`/form data into operation
keyword arguments. Its result must be either a complete typed argument mapping
or an existing Chirp validation result. The operation is not called when
binding or server authorization fails.

## 5. Stable identity and compilation

### 5.1 Identity

The canonical operation ID is Milo's dotted command path as returned by
`CLI.walk_commands()` and accepted by `CLI.get_command()`/`CLI.call()`:

```text
work-items.create
```

That exact value is used in adapter declarations, contract diagnostics,
DevTools traces, WebMCP `toolname`, MCP tool names, MCP App metadata, and
future inspection records. The human CLI renders it as `work-items create`,
but the space-separated spelling is presentation, not identity.

Aliases are accepted by Milo's CLI but are not universal identities. Renaming
the dotted canonical path is a compatibility change and requires migration
guidance. Object identity, registration order, absolute paths, function
qualnames, and route paths do not participate.

### 5.2 Freeze lifecycle

The adapter resolves declarations during the existing app freeze lock:

1. resolve each dotted ID against the supplied `CLI`;
2. reject duplicates and missing/lazy-import-failed commands;
3. validate the callable tier and projection combinations;
4. register ordinary Chirp routes and template declarations;
5. compile operation nodes and projection transitions into the private
   `HypermediaProgram`; and
6. publish only immutable, deterministically sorted runtime records.

The graph may record transitions such as operation-to-route,
operation-to-template, operation-to-block, operation-to-form, and
operation-to-agent-tool. `RenderPlan` remains the request-aware rendering
authority. The internal graph remains private; issue #573 owns any future
public inspection surface.

No request path introspects decorators, walks templates, imports a lazy command,
or mutates an allowlist. Multiple worker threads share the frozen records.

## 6. Inputs, contexts, and server authority

### 6.1 Typed core callable

The universal callable contains domain inputs only. Its schema-visible
parameters must be reproducible across CLI and agent surfaces. It must not
accept:

- `chirp.Request`;
- raw ASGI scope/receive/send values;
- a generic universal context bag;
- a browser session object; or
- a Chirp return type as an input.

Application services may be captured through a closure or injected through a
documented application/service boundary that is not schema-visible.

### 6.2 Chirp Request and Milo Context stay distinct

The web binder and authorization function may receive Chirp's `Request`.
Milo's CLI/MCP runtime may inject Milo `Context` into a Milo command, but an
operation with that injection point is not eligible for a web projection in
the first tier. Chirp will not synthesize a partial `Context`, and Milo will not
receive a fake HTTP request.

If a future Milo service-injection protocol can prove the same callable across
surfaces without exposing context in its schema, that requires an RFC
amendment. Until then, a command with `Context` is CLI/MCP-only.

### 6.3 Validation

Milo's schema is authoritative for parameter names, scalar/container types,
requiredness, defaults, descriptions, and supported annotation constraints.
Chirp's form binder is authoritative for decoding untrusted HTTP bytes and
producing user-visible field errors.

At freeze, `app.check()` compares the declared form fields with Milo's schema.
Missing required fields, unexpected fields, incompatible multiplicity, and
incompatible constraints are errors that name the operation, template, block,
field, and mismatch. This is a drift check, not schema-driven form generation.
The application still writes the one real HTML form in Kida.

The operation itself must preserve domain invariants regardless of caller.
Browser-side or CLI-side checks are conveniences, not authority.

### 6.4 Authentication, authorization, and confirmation

No exposure inherits authority from another surface:

- Chirp middleware and the binding's authorization policy govern HTTP, htmx,
  and WebMCP submissions;
- Milo middleware and command confirmation govern CLI and ordinary MCP;
- MCP App actions return through a server-authorized tool call rather than
  treating resource HTML as permission; and
- CSRF, origin, session, rate-limit, and audit policy remain active on the
  server path that already owns them.

Milo annotations are behavioral hints, not enforcement. A mutation binding
must declare an authorization function and a confirmation posture. A
`destructiveHint` mismatch, WebMCP autosubmit on a mutation, missing policy, or
an MCP App that bypasses the operation tool is a startup error.

## 7. Result and failure mapping

The operation returns a typed domain value or raises a typed domain/Milo error.
Each surface projects that same outcome through its native contract.

| Outcome | Browser / htmx | CLI / programmatic | MCP | WebMCP | MCP App |
| --- | --- | --- | --- | --- | --- |
| Success | `render(result)` returns existing Chirp return type | Milo formats or returns typed value | Milo text plus schema-compatible `structuredContent` | Same server form response as browser | Milo tool result plus Chirp-rendered named block |
| Input error | Existing `ValidationError`/form fragment; no operation call | Milo parse/schema error and nonzero exit | MCP `isError` with repair context | Same server validation HTML | Tool error; UI stays renderable |
| Unauthorized | Normal Chirp security response; no operation call | Milo middleware error | MCP tool error | Same server security response | Tool error; resource grants no authority |
| Domain conflict | Explicit web projector mapping, normally `409` plus named block | Typed Milo/domain error | Structured tool error | Same HTTP response | Tool error and optional refreshed block |
| Missing required block | `BlockNotFoundError`; never empty HTML | Not applicable | Not applicable unless UI requested | `BlockNotFoundError` on web response | Resource/tool rendering fails loud |
| Unexpected exception | Existing Chirp error pipeline | Milo nonzero/error behavior | MCP tool error | Same Chirp error pipeline | Tool error; no fabricated success UI |

An operation result is not itself `Page`, `Fragment`, `Response`, `Stream`, or
`EventStream`. Those values are web projection results. Conversely, the web
projector does not convert HTML into MCP `structuredContent`.

Milo `0.3.1` can derive an `outputSchema` from a return annotation. Its MCP path
uses string conversion for the text view, then places every non-string,
non-`None` result unchanged in `structuredContent`. An arbitrary dataclass is
therefore stringified for text but remains non-JSON-native in
`structuredContent`; typed dataclass parity is not proven. The first
implementation must do one of the following before claiming it:

1. consume a Milo release that serializes its supported typed return models in
   conformance with `outputSchema`; or
2. limit the published compatibility tier to a Milo-supported structured
   return shape such as a typed dictionary.

Chirp's adapter must not close that gap with a generic serializer. The
canonical prototype should use a frozen, slotted domain result only after the
Milo path can prove it; otherwise it uses a `TypedDict` and records the reduced
tier.

## 8. Sync, async, cancellation, and streaming

### 8.1 First compatibility tier

The first tier accepts synchronous, finite callables. This matches Milo
`0.3.1`'s `CLI.call()`/`call_raw()` behavior and avoids running a coroutine as a
value on CLI/MCP surfaces. The adapter rejects coroutine functions and
awaitable results during setup/prototype proof with an actionable error.

Chirp may execute the synchronous operation through its established sync
handler boundary. Any thread offload must preserve existing request context
rules and be measured; this RFC does not authorize sync-fast-path changes.

### 8.2 Async

Async universal operations are **not supported** in the first tier. Promotion
requires a public Milo async invocation contract, CLI and MCP tests, Chirp
request-context isolation proof, error parity, and cancellation behavior. A
Chirp-only async wrapper would not be universal and is rejected.

### 8.3 Cancellation

Client disconnects, `Ctrl+C`, MCP cancellation or host disconnects, and browser
navigation have different lifecycles. The first tier does not claim
cross-surface cancellation. Once execution begins, the domain operation
follows the owning runtime's existing cancellation behavior. A future tier
must define an idempotency/rollback boundary before forwarding cancellation
into mutations.

### 8.4 Streaming

Milo generators yielding `Progress` are protocol progress, not HTML chunks.
Chirp's streaming return types remain distinct:

- `Stream` progressively sends first-byte HTML;
- `Suspense` sends a shell and deferred OOB blocks; and
- `EventStream` sends post-load SSE updates.

None is a universal operation result. The first tier rejects generator and
async-generator operations. A future streaming projection needs typed progress
and terminal-result semantics in Milo plus an explicit mapping for every
surface; it may not route JSON chunks through the render pipeline.

## 9. Surface parity matrix

| Surface | Registration | Input | Success output | Error contract | Unsupported in first tier |
| --- | --- | --- | --- | --- | --- |
| Browser HTTP | Explicit `WebProjection` | Real form decoded by binder | Existing Chirp return type from one template | Chirp status/error/validation pipeline | Schema-generated page, JSON fallback |
| htmx | Same web binding and route | Same real form, htmx headers | Named block/OOB through normal negotiation | Fail-loud block and normal status behavior | Parallel partial template |
| Human CLI | Milo command | Milo parser | Milo formatter | Milo exit/stderr contract | Chirp HTML formatting |
| Programmatic CLI | Milo dotted path | `CLI.call()` kwargs | Typed value | Raised error | HTTP request context |
| MCP tool | Explicit adapter allowlist | Milo input schema | Milo content plus compatible structured result | Milo MCP tool error | Auto-expose every command |
| WebMCP | Explicit `webmcp=True` on a web binding | Browser fills/submits same HTML form | Same HTTP/htmx response | Same server error/validation path | Imperative duplicate tool, JSON-LD response claim |
| MCP App | Explicit `MCPAppProjection` | Milo tool call | Milo typed result plus Chirp block resource | Tool error; missing block fails loud | Resource HTML as authorization, separate UI template |

Every implementation increment must test success, invalid input, unauthorized
access, and an unsupported combination for the surfaces it claims. A surface
is not “parity complete” because it appears in discovery.

## 10. WebMCP preview boundary

WebMCP is experimental and must remain isolated behind an explicit preview
capability. The first preview uses only the declarative form vocabulary
verified at the pinned proposal commit:

- `toolname` and `tooldescription` on the real `<form>`;
- normal control `name` and `required` attributes;
- `toolparamdescription` on controls; and
- optional boolean `toolautosubmit` only where policy permits.

The stable dotted operation ID is emitted as `toolname`. A non-destructive form
may opt into autosubmit only after an explicit policy decision. A mutation,
destructive command, ambiguous command, file upload, or confirmation-requiring
command must omit `toolautosubmit`, leaving the browser to focus the submit
control for human review.

The first preview does not use `document.modelContext.registerTool()`, does not
ship a JavaScript tool registry, does not invent JSON-LD response semantics,
and does not depend on proposed `SubmitEvent.agentInvoked`/`respondWith`
behavior. Browser absence changes nothing: the form remains usable by normal
HTTP and htmx clients.

Because the proposal's schema synthesis and cross-document response behavior
are still under discussion, Chirp documents no stronger compatibility claim.
Tests must assert the exact emitted attributes, no mutation autosubmit, no
duplicate imperative registration, and an unchanged no-WebMCP fallback.

## 11. MCP Apps boundary

Milo owns MCP App protocol mechanics: `ui://` resource registration, metadata,
MIME/profile negotiation, capabilities, tool/resource linkage, gateway
behavior, and protocol errors. Chirp owns the resource HTML supplied to that
mechanism.

`MCPAppProjection` identifies one existing Kida template and named block. The
adapter renders that block through Chirp's existing render plan with an
explicit application-provided view context. The block is the initial tool UI
shell; the operation result travels through Milo's tool-result protocol rather
than through bridge-global state. The block belongs to the same template used
for the browser page and htmx fragments. It is not a second “MCP template.”

The resource is read-only presentation. Mutations flow back through the
explicit Milo operation tool and its server authorization. The resource must
not contain ambient credentials, private request state, or a bypass endpoint.
CSP, sanitization, embedding policy, and host negotiation must be decided with
Milo issue #74 before the preview can ship.

The bridge must not cache “the latest operation result” for resource rendering:
that would leak state across users and workers. Result-driven UI updates use
the host/tool-result mechanism Milo defines, or an application-owned,
authorized stable read model supplied explicitly to a later resource read.

A missing `ui://` capability or unsupported client receives Milo's protocol
fallback; it does not weaken the ordinary MCP tool. A missing named block or
empty required render fails loud and is reported by `app.check()`.

## 12. Explicit exposure and allowlists

Milo `0.3.1` exposes every non-hidden command from a `CLI` through its ordinary
MCP `tools/list`. That default is too broad for a Chirp universal-operation
bridge. `mcp=True` therefore means “include this command in the adapter's
published MCP view,” not “the source CLI happens to contain it.”

The implementation must use a Milo-owned allowlist/sub-CLI capability or a
public, reviewed adapter mechanism. It must not mutate Milo's private command
dictionary or use `hidden` as a security control. Until such a capability is
available, explicit MCP publication is blocked; HTTP-only bindings may still
be prototyped.

The same closed-default rule applies independently to WebMCP and MCP Apps.
`app.check()` reports any tool present in the adapter's published view that
lacks a matching explicit projection declaration. Commands that exist only in
the source CLI are outside that view and remain closed without a warning.

## 13. Existing `chirp.tools` migration

Chirp currently has a provisional `@app.tool()` surface, `ToolDef`,
`ToolRegistry`, local `function_to_schema()`, and MCP handler. This RFC does not
pretend that surface is Milo and does not register the same callable in both
systems automatically.

The migration order is:

1. keep current behavior and compatibility tests unchanged;
2. implement and prove the optional Milo adapter on a separate example;
3. add a contract diagnostic for duplicate public tool identity across the
   registries;
4. publish a side-by-side migration guide, including approval/session behavior;
5. deprecate the old surface only through a public-API review and changelog;
6. remove it only in a release permitted by `docs/release-policy.md`.

There is no compatibility shim that converts `ToolDef` into `CommandDef` at
request time. Current users remain on the current registry until they opt into
the reviewed migration.

## 14. Contract checks and diagnostics

The adapter adds startup diagnostics where setup-time evidence exists. The
proposed severity policy is part of this RFC and still requires implementation
tests before activation.

| Condition | Severity | Required message context |
| --- | --- | --- |
| Missing or duplicate operation identity | ERROR | dotted ID and registrations |
| Binding after freeze | immediate configuration error | dotted ID and lifecycle fix |
| Unsupported async/generator/context callable | ERROR | dotted ID and supported tier |
| Web route/method collision | ERROR | dotted ID, method, route, conflicting handler |
| Required form field missing or incompatible | ERROR | dotted ID, template/block, field, schema constraint |
| Required template/block absent or empty | ERROR | dotted ID, template, block, projection |
| Mutation lacks authorization/confirmation posture | ERROR | dotted ID and missing policy |
| WebMCP mutation requests autosubmit | ERROR | dotted ID and form block |
| Agent surface discovered without explicit allowlist | ERROR | dotted ID and surface |
| Annotation/projection safety mismatch | ERROR | dotted ID, annotation, projection |
| Adapter binding declares no projection | ERROR | dotted ID and available opt-ins |

Missing-block behavior must retain `BlockNotFoundError` propagation at render
time even when a startup check also reports the configuration. A diagnostic is
not permission to emit an empty swap or UI resource.

The checks consume frozen compiler records, not live registries. Categories,
messages, severities, production/debug behavior, and `raise_on_error` handling
need end-to-end `app.check()` tests.

## 15. Canonical prototype: create a work item

Issue #580 should prove the design with one deliberately small operation:

- canonical identity `work-items.create`;
- typed inputs `title` and `priority`, including required/default/constraint
  evidence;
- one typed `WorkItemReceipt` result when Milo supports conforming structured
  serialization, otherwise an explicitly documented `TypedDict` tier;
- one `work_items.html` template with named blocks `page_root`, `create_form`,
  `work_item_row`, and `create_tool`;
- normal POST plus htmx fragment/OOB behavior from that template;
- malformed and domain-invalid form proof;
- unauthorized mutation proof;
- human CLI and `CLI.call()` proof;
- allowlisted ordinary MCP discovery/call proof;
- declarative WebMCP attributes and browser-absence fallback;
- MCP App `ui://` resource from `create_tool`; and
- fail-loud proof for a missing required block.

The example must be executable, install the optional extra explicitly, and be
used by docs rather than duplicated as an untested snippet. It must not use a
mock JSON endpoint, a second partial template tree, or a tool-only mutation
path.

## 16. Public API and collateral contract

Runtime implementation is incomplete until these surfaces agree:

| Surface | Required collateral |
| --- | --- |
| Optional dependency | `pyproject.toml` extra, lockfile, missing-extra import test and actionable install guidance |
| Public imports | adapter exports, `docs/public-api.md`, import tests, changelog/migration notes |
| Setup API | frozen/slotted records, lifecycle tests, API reference, runnable example |
| Compiler | immutable graph records, deterministic identity tests, freeze/concurrency proof |
| HTTP/htmx | `TestClient` success/error/authorization/missing-block contract tests |
| CLI/MCP | pinned Milo compatibility tests and surface-diff proof |
| WebMCP | preview docs, exact attribute tests, browser fallback, security warning |
| MCP Apps | Milo compatibility pin, `ui://` negotiation/fallback tests, CSP/security notes |
| Existing tools | migration guide, duplicate-ID rule, no-regression tests |
| Scaffolds | no default exposure; add only after the preview is promoted |
| Site | compatibility tier and executable example; no generated output hand edits |
| Release | towncrier fragment and migration guidance for any public behavior |

The initial adapter lives under `chirp.ext` so importing `chirp` remains safe
without Milo. Whether `use_milo` is eventually re-exported from `chirp` is a
separate public-API decision; this RFC does not require a top-level export.

## 17. Compatibility gates and dependencies

Implementation is gated by:

1. **CLI contract (#571):** Chirp's own CLI behavior and Milo adoption gaps are
   recorded before deeper coupling.
2. **Milo allowlist:** a public way to publish selected commands without
   private registry mutation.
3. **Typed structured result parity:** Milo's MCP result must conform to the
   advertised return schema for the result shape the prototype claims.
4. **Adapter (#577):** optional dependency, lazy import, identity resolution,
   and lifecycle boundary.
5. **WebMCP (#574):** declarative preview after the core binding exists.
6. **MCP Apps (#578 / Milo #74 and #79):** protocol/resource primitive before
   Chirp UI projection.
7. **Canonical proof (#580):** all claimed surfaces converge on one operation
   and one template.

The internal compiler work from saga #503 is substrate, not a public graph API.
Issue #573 may expose an allowlisted read model later, but this RFC does not
wait for or pre-design that public inspection shape.

## 18. Alternatives considered

### 18.1 New `@app.operation` decorator — rejected

It would duplicate Milo command registration and schema generation, forcing
applications to choose or synchronize two definitions. The optional bridge
must consume Milo's existing public command model.

### 18.2 Make every Chirp route a tool — rejected

Routes often include navigation, private implementation endpoints, streaming
transports, and request-shaped parameters. Automatic exposure violates least
authority and cannot infer confirmation or meaningful tool descriptions.

### 18.3 Return Chirp types from the core operation — rejected

That makes the CLI/MCP domain function understand HTML rendering and gives
non-web surfaces an unusable value. Existing Chirp types belong in the web
projector.

### 18.4 Generate HTML forms from JSON Schema — rejected

Schema does not carry the layout, copy, progressive enhancement, accessibility,
or named-block contract of a real page. Chirp checks a hand-authored form
against the schema; it does not replace the template.

### 18.5 Serialize operation results in Chirp — rejected

A generic serializer would be a REST-style side channel and duplicate Milo.
Milo owns generic output. Chirp maps typed values directly into templates.

### 18.6 One universal context object — rejected

HTTP requests, CLI terminal state, and MCP sessions have different security
and lifecycle semantics. A bag of optional fields makes authority ambiguous
and schemas unstable.

### 18.7 Treat WebMCP imperative tools as the primary browser path — rejected

It would require a JavaScript registry and duplicate the form submission path.
Declarative enhancement preserves the real server-owned form and no-JavaScript
fallback.

## 19. Non-goals and not-now items

- No JSON API or generic `make_response()` path.
- No new Chirp return type.
- No `AppConfig` feature flag.
- No mandatory Milo dependency.
- No automatic route, tool, WebMCP, or MCP App exposure.
- No generated forms or templates from schema.
- No async, cancellation, or universal streaming claim in the first tier.
- No conversion of `Stream`, `Suspense`, or `EventStream` into MCP progress.
- No public `HypermediaProgram` dataclasses.
- No automatic migration/removal of `app.tool()`.
- No WebMCP imperative JavaScript registry or unverified response extension.
- No MCP App protocol implementation inside Chirp.
- No scaffold default until security and fallback proof support promotion.

## 20. Steward synthesis

The RFC consulted the `src/chirp/tools`, `src/chirp/contracts`,
`src/chirp/templating`, `src/chirp/http`, `src/chirp/validation`,
`src/chirp/ext`, and docs steward contracts.

### Accepted findings

```text
Steward: Templating
Area: Universal result-to-HTML projection
Severity: P0
Invariant: One Kida template and named blocks remain the render surface; missing required blocks fail loud.
Evidence: AGENTS.md:11-14,35-40; src/chirp/templating/AGENTS.md:15-16,29-32
User Impact: A parallel agent template or empty missing-block fallback would make browser and agent UI disagree and could erase visible content.
Required Fix: Keep HTML mapping in existing Chirp return types/render plans and require BlockNotFoundError for absent blocks.
Required Proof: TestClient and MCP App resource tests for shared blocks and missing-block propagation.
Collateral: Executable prototype, template docs, app.check diagnostics, changelog when behavior ships.
Confidence: High
Verification Status:
machine-verified
```

```text
Steward: Tools
Area: Registry, schema, and exposure ownership
Severity: P0
Invariant: The adapter must not create a second operation registry/schema compiler or auto-expose commands.
Evidence: src/chirp/tools/registry.py:8-9,36-47; src/chirp/tools/schema.py:26-64; Milo 0.3.1 src/milo/_command_defs.py:47-65, src/milo/commands.py:583-601,1289-1317, and src/milo/mcp.py:316-355,441-443 at commit 1f5370861fa38bc7942111a623fa2cb5a7f567b9
User Impact: Duplicate definitions drift, while automatic publication turns local commands into remote authority.
Required Fix: Resolve explicit Milo dotted IDs, require per-surface allowlists, and migrate the provisional Chirp registry separately.
Required Proof: Identity, duplicate, freeze, allowlist, and current-tools no-regression tests.
Collateral: Migration guide, public API docs, release note when deprecation begins.
Confidence: High
Verification Status:
machine-verified
```

```text
Steward: Contracts
Area: Startup diagnostics and severity
Severity: P1
Invariant: Detectable wiring and security mistakes are actionable at startup without weakening runtime failures.
Evidence: AGENTS.md:35-40; src/chirp/contracts/AGENTS.md:39,80
User Impact: Field drift, missing blocks, or unsafe mutation exposure otherwise appear only after an agent or user invokes the path.
Required Fix: Compile immutable projection edges and add specific ERROR diagnostics; retain runtime BlockNotFoundError.
Required Proof: End-to-end app.check categories, messages, severities, raise_on_error, debug, and production tests.
Collateral: Contracts reference and example failure guidance.
Confidence: High
Verification Status:
machine-verified
```

```text
Steward: HTTP and Validation
Area: Request binding and server authority
Severity: P1
Invariant: Untrusted HTTP input is decoded and authorized through Chirp's existing request/form pipeline before the domain operation runs.
Evidence: src/chirp/http/AGENTS.md:19-28,56-60; src/chirp/validation/AGENTS.md:17-30,47-57
User Impact: Treating browser/agent schema validation as authority would bypass CSRF, session, field-error, and domain-validation behavior.
Required Fix: Keep Request in the web binder, compare form declarations at freeze, and test that failed binding/authorization never calls the operation.
Required Proof: Malformed, invalid, unauthorized, htmx, and non-htmx TestClient tests.
Collateral: Security notes and executable form example.
Confidence: High
Verification Status:
machine-verified
```

```text
Steward: Extensions
Area: Optional Milo dependency and lifecycle
Severity: P1
Invariant: Core Chirp imports remain safe without Milo, and adapter state freezes before concurrent request use.
Evidence: AGENTS.md:30-35,266-270; src/chirp/ext/AGENTS.md:3,18-21,47-53
User Impact: A mandatory import breaks core users; mutable runtime registrations create worker-dependent exposure.
Required Fix: Use a lazy optional adapter, actionable missing-extra error, setup-only registration, and immutable published records.
Required Proof: Missing/present-extra imports, post-freeze rejection, deterministic compilation, and concurrency tests.
Collateral: Extra declaration, lockfile, install docs, public API notes, changelog.
Confidence: High
Verification Status:
machine-verified
```

### Convergence

The templating and tools stewards independently reject a second render or
serialization path. Under the repository convergence rule, this is accepted as
P0: the bridge must pass typed values directly to Chirp's existing render plan
and leave generic structured output to Milo. The tools and extensions stewards
also converge on immutable explicit exposure; no request-time registry is
permitted.

### Minority reports

The most convenient alternative is to auto-generate a web form and JSON result
from Milo's schemas. It would reduce setup code, but it cannot express Chirp's
layout, named blocks, htmx negotiation, validation display, or fail-loud
semantics. The RFC rejects that convenience in favor of an explicit binder and
renderer.

Another possible first tier would support async only on web while leaving
CLI/MCP sync. That is useful but not universal. The RFC records it as not-now
until Milo has an async invocation contract.

### Ranked implementation backlog

1. Milo allowlist and typed structured-result compatibility gaps.
2. Optional adapter core: identity, lifecycle, binding, and missing-extra
   behavior (#577).
3. Compiler and `app.check()` projection edges.
4. Canonical browser/htmx/CLI/ordinary-MCP slice.
5. Declarative WebMCP preview (#574).
6. Milo MCP App resource integration (#578, Milo #74/#79).
7. Full canonical proof and surface-diff gate (#580).
8. Separately reviewed `chirp.tools` migration.

## 21. Acceptance criteria

This design is ready to implement when reviewers agree that it:

- assigns stable identity and generic schema/CLI/MCP ownership to Milo;
- assigns HTTP, validation display, HTML, htmx, blocks, and return types to
  Chirp;
- keeps Request and Milo Context distinct;
- requires explicit per-surface registration and an enforceable MCP allowlist;
- maps success and error outcomes for all seven surfaces;
- defines unsupported async, cancellation, and streaming behavior;
- pins the exact experimental WebMCP vocabulary and fallback boundary;
- places MCP App protocol mechanics with Milo and resource HTML with Chirp;
- preserves and plans a safe migration for current `chirp.tools` users;
- names public API, optional dependency, docs, examples, scaffold, test,
  security, compiler, and changelog collateral; and
- gives issue #580 an executable one-template prototype contract.

Any implementation PR that broadens these boundaries must update this RFC and
repeat the affected steward review before it ships.
