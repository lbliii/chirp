# Hypermedia Application Compiler

**Status:** Proposed product and architecture strategy
**Updated:** 2026-07-01
**Scope:** Directional guidance, not documentation of a shipped graph API

## Thesis

Chirp is a full-stack Python hypermedia framework with the foundations of a
built-in application compiler.

Developers write Python routes, typed return values, and HTML templates with
named blocks. Chirp can compile those declarations and discoverable
relationships into an inspectable application model, validate that model, and
execute request-specific render plans from it.

The user-facing outcome is:

> Build complete database-backed web applications in Python and HTML, catch
> broken interactions before the browser, and export static-compatible routes
> when static hosting is useful.

The compiler is the mechanism and differentiator. The product remains a
framework for running real applications.

## Vocabulary

Three concepts must remain distinct:

| Concept | Meaning |
| --- | --- |
| Application compilation | The setup-to-runtime process that resolves routes, templates, blocks, registries, contracts, and runtime wiring into an executable application. Every Chirp application does this. |
| Live application runtime | The primary deployment model: an ASGI application serving request-time behavior such as SQL, forms, sessions, authentication, streaming, SSE, tools, and AI work. |
| Static export | The optional `chirp freeze` capability that materializes compatible routes as files for static hosting. It is one output path, not the definition of compilation. |

Internally, `App.freeze()` is the lifecycle boundary that prevents registration
after runtime publication. Public positioning should call this application
compilation or startup compilation so it is not confused with the `chirp
freeze` static-export command.

## Recommended Positioning

Use a three-layer message:

1. **Outcome:** Build complete web applications in Python and HTML without a
   SPA or JavaScript build pipeline.
2. **Differentiator:** Chirp validates routes, templates, fragments, forms,
   streaming, and live updates as one application contract.
3. **Mechanism:** A built-in hypermedia application compiler turns typed return
   values and named template blocks into executable render plans.

Recommended short description:

> Chirp is a full-stack Python hypermedia framework with a built-in contract
> compiler.

Recommended expanded description:

> Chirp compiles Python routes, typed return values, and HTML templates into a
> validated hypermedia application. Run the full application with databases,
> mutations, streaming, and SSE; export static-compatible routes when you want
> cheap static deployment.

“Hypermedia engine” is accurate but less differentiated. “Hypermedia
compiler” should be used when the surrounding copy makes clear that the output
is an executable live application, not merely static files.

## What Exists Today

This direction doubles down on existing architecture rather than replacing it:

- Typed returns such as `Page`, `Fragment`, `OOB`, `Suspense`, `EventStream`,
  `ValidationError`, and `MutationResult` already express render intent.
- `src/chirp/templating/render_plan.py` normalizes request-aware composition
  into an immutable `RenderPlan` before rendering and serialization.
- `src/chirp/app/compiler.py` already owns the setup-to-runtime compilation
  boundary.
- `ContractCheckSnapshot` already gathers routes, templates, page metadata,
  registries, layout chains, signals, settings, security declarations, and
  plugin data for `app.check()`.
- Kida exposes template and block metadata, including block dependencies.
- `app.check()` already validates route/template/htmx/OOB/Suspense/SSE/form,
  security, accessibility, reactive, and deployment relationships.
- Chirp DevTools already records typed-return traces, render-plan data, htmx
  lifecycle evidence, Swap Doctor findings, and SSE lifecycle traces.
- `chirp freeze` can already render compatible application routes into static
  output without creating a separate template system.

These are compiler ingredients. What does not yet exist is one authoritative,
stable artifact connecting all of them.

## The Missing Center

The target is a frozen, inspectable internal read model, provisionally called
`HypermediaProgram`:

```python
@dataclass(frozen=True, slots=True)
class HypermediaProgram:
    routes: tuple[RouteNode, ...]
    templates: tuple[TemplateNode, ...]
    blocks: tuple[BlockNode, ...]
    targets: tuple[TargetNode, ...]
    transitions: tuple[TransitionEdge, ...]
    origins: tuple[SourceOrigin, ...]
```

This sketch is directional. Names and public exposure require design review.
The important decision is that one immutable model becomes the shared source
for checks, runtime trace correlation, DevTools, testing, documentation, and
static export analysis.

```text
routes + return declarations + template metadata + registries
                              |
                              v
                   HypermediaProgram
                              |
          +-------------------+-------------------+
          |                   |                   |
          v                   v                   v
    live ASGI runtime     app.check()       static export
          |                   |                   |
          +------------ DevTools/tests -----------+
```

## Program Contents

The compiled model should be able to represent:

- routes, methods, parameters, names, mounts, and handler origins;
- possible typed return intents and request-mode negotiation;
- templates, layouts, named blocks, block dependencies, and composition;
- full, boosted, fragment-targeted, OOB, Suspense, streaming, and SSE paths;
- htmx targets, selectors, swap modes, and fragment-target registrations;
- mutation forms, validation paths, CSRF posture, and non-JavaScript fallbacks;
- OOB and SSE producers matched to reachable consumers;
- signals, reactive dependencies, and audience scope;
- static-export eligibility and the reason a route requires runtime execution;
- stable source origins for inferred and explicitly declared facts.

The model must distinguish a fact inferred from source from a fact explicitly
declared by a dynamic registry. Inference should reduce boilerplate; validated
declarations should cover behavior that static analysis cannot honestly know.

## Primary Consumers

### Live runtime

The runtime is the primary consumer. It should execute request-specific render
plans while supporting SQLite/PostgreSQL, forms, sessions, authentication,
uploads, streaming, SSE, tools, and AI inference. Compiler work must not turn
live applications into a secondary use case.

### Contract checks

Checks should become graph queries instead of repeatedly reconstructing partial
relationships. Diagnostics should identify the exact route, template, block,
target, transition, declaration origin, and next action.

### DevTools

Runtime traces should carry stable compiled node and transition identities.
DevTools can then show not only what happened, but which declared application
edge was executed and why that render plan was selected.

### Tests and coverage

Coverage should progress from aggregate counters to transition evidence:

- normal navigation;
- boosted navigation;
- narrow fragment requests;
- valid and invalid mutation paths;
- non-JavaScript fallbacks;
- OOB updates;
- Suspense resolution, including falsy values;
- SSE delivery and reconnect paths.

### Static export

Static export should ask the compiled model which routes and dependencies can
be evaluated ahead of time. Runtime-only routes remain ordinary live
application behavior. Mixed applications may have both static-compatible and
runtime-required surfaces.

### Agents and developer tools

Structured diagnostics make Chirp applications unusually legible to coding
agents. A useful closed loop is:

```text
write feature -> compile -> diagnose broken edge -> apply bounded fix
              -> route-smoke -> observe runtime transition
```

This is a consequence of explicit application contracts, not a separate AI
abstraction or generated business-logic layer.

## The Product Proof

The vision should be demonstrated with a real database-backed application, not
only a static site or isolated feature gallery. A short demonstration should:

1. Run an application with SQL, search, forms, validation, boosted navigation,
   and an SSE region.
2. Show the same template serving full-page and named-block access patterns.
3. Introduce a full-document-in-fragment error, a missing OOB block, and an
   unsafe mutation path.
4. Run `chirp check` and receive precise, actionable diagnostics.
5. Show the matching render transitions in Chirp DevTools.
6. Export only the static-compatible surface while leaving dynamic routes in
   the live application.

Furatena is the downstream proof that these pressures are real. It should
remain an independent product and compatibility canary, not become framework
code or a bundled starter application.

## Delivery Strategy

This should be an incremental consolidation, not a rewrite:

1. Define stable internal graph nodes, transitions, and source origins.
2. Build the graph during the existing compilation boundary.
3. Adapt current contract rules to query it one domain at a time.
4. Provide explicit declarations for dynamic reachability.
5. Make structured inspection the primary result; render terminal and JSON
   presentations from it.
6. Correlate runtime traces and tests with stable transition identities.
7. Productize the proof only after diagnostics are trustworthy.

Existing return types, route decorators, templates, render plans, and runtime
behavior should remain valid throughout the migration. A second graph or
parallel rendering pipeline would defeat the purpose.

## Non-Goals

- Turning Chirp into a static-site generator first.
- Replacing the live ASGI runtime with ahead-of-time HTML generation.
- Adding a JSON/SPA side channel to model client behavior.
- Building an ORM, admin product, client state manager, or JavaScript compiler.
- Replacing behavioral browser tests with static analysis.
- Claiming that arbitrary Python business logic can be statically understood.
- Making the compiler graph public before its identity, compatibility, and
  extension contracts are designed.

## Claim Readiness

The positioning can mature in stages:

| Stage | Defensible claim |
| --- | --- |
| Today | Chirp is a typed hypermedia framework with unusually strong application contract checks. |
| Compiler foundation | Chirp compiles routes, return intents, templates, and registries into one validated internal application model. |
| Observable compiler | Static checks, runtime traces, and tests refer to the same compiled transitions. |
| Productized compiler | Developers can inspect, diff, test, and document the compiled application through stable tooling. |

Marketing should not outrun the corresponding stage.

## Success Criteria

The vision is credible when:

- a substantial database-backed consumer passes without fake source references
  or blanket check suppressions;
- normal, boosted, fragment, mutation, OOB, Suspense, and SSE transitions are
  represented with stable identities;
- structured inspection and terminal checks contain the same findings;
- runtime traces correlate to compiled transitions;
- transition coverage identifies important unexercised paths;
- the five-minute product proof catches recognizable browser-facing failures;
- static export is clearly shown as an optional target of the same application
  model;
- public APIs and extension points have explicit compatibility status.

## Related Work

- `docs/philosophy.md`
- `docs/devtools.md`
- `docs/rfcs/002-resolution-as-data.md`
- `plan/drafted/epic-hypermedia-application-compiler.md`
- `plan/drafted/epic-downstream-product-success.md`
- [GitHub saga #503](https://github.com/lbliii/chirp/issues/503) and epics
  [#504](https://github.com/lbliii/chirp/issues/504)-[#508](https://github.com/lbliii/chirp/issues/508)
- Foundation issues #497-#502 and implementation issues #509-#513
