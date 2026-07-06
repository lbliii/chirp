# RFC 008: Internal Hypermedia Program

**Status:** Accepted — first increment implemented by issue #509
**Scope:** Internal startup compilation; no public graph or inspection API

## Context

Chirp already compiles routes and middleware, discovers Kida templates and
blocks, freezes target registries, and builds a stable snapshot for
`app.check()`. Those facts were previously consumed as separate collections.
That made it difficult for checks, traces, and tests to refer to the same
relationship without reconstructing another partial graph.

The first compiler increment needs one immutable read model without changing
the request-aware render plan, contract severity policy, CLI, or public API.

## Decision

`AppCompiler.freeze()` builds an internal `HypermediaProgram` after the router
and Kida environment are complete and before registries and runtime state are
published. The program contains frozen, slotted records for:

- method-specific routes;
- registered or route-declared templates and their load status;
- named blocks scoped to a template;
- registered htmx targets;
- route-to-template, route-to-block, template-to-block, and target-to-block
  transitions;
- source origins and inferred-versus-declared provenance.

The program is stored on `RuntimeAppState` and passed privately through
`ContractCheckSnapshot`. It is not exported from `chirp`, and `_hypermedia_program`
is not a supported plugin or inspection surface.

`RenderPlan` remains the request-aware execution authority. The program
describes compiled relationships; it does not render, negotiate requests, or
create a parallel template path.

## Stable identities

Identities are semantic strings built from a node kind and percent-encoded
parts. Registration order, object identity, hash randomization, and absolute
filesystem paths never participate.

| Record | Identity inputs |
| --- | --- |
| Route | HTTP method + registered path |
| Template | loader-relative logical template name |
| Block | logical template name + block name |
| Target | normalized target ID without `#` |
| Transition | transition kind + source ID + destination ID |

Equivalent registrations therefore compile to identical ordered tuples.
Duplicate identities raise `ConfigurationError` with the conflicting identity.
All tuple collections are sorted by stable ID before publication.

## Origins and provenance

`SourceOrigin` stores a public-safe logical identifier:

- handlers use `module:qualname` and an optional source line;
- templates use their loader-relative logical name;
- target declarations use the contract name or normalized target ID;

Origins do not store absolute template paths or runtime values. `declared`
provenance means the application or a registered contract supplied the edge;
`inferred` means Chirp derived it from existing Kida/router metadata.

## Validation and failure policy

The graph validator rejects duplicate identities, unknown transition sources,
and resolved edges whose destination is absent. References that existing
contract checks diagnose—such as an unknown declared template or block—remain
as unresolved edges. `app.check()` continues to emit the same actionable
category and severity instead of moving those failures to a new policy layer.

The first two migrated consumers are the page-shell and fragment-target-orphan
rules. They query compiled target-to-block transitions while preserving their
existing messages and severity behavior.

## Lifecycle and free-threading

Compilation runs under the existing app freeze lock. A complete program is
assigned once before `RuntimeAppState.frozen` becomes true. Its records and
collections are frozen dataclasses and tuples, so request workers and contract
checks share one read-only object without a new lock or post-freeze mutation.

## Extension boundary

This increment deliberately has no public extension protocol. Issue #498 may
add validated dynamic reachability declarations as setup-time inputs to this
same compiler. Issues #510 and #511 may design stable public inspection and
trace views, but they must not expose these internal dataclasses by accident.

Future consumers migrate one relationship family at a time. The old input is
removed from each migrated rule so the program becomes the shared source of
truth rather than a permanent second graph.

## Consequences

- Contract rules can share deterministic compiled relationships.
- Runtime traces and tests have stable identities to build on.
- Template parse failures are recorded once in the model and remain visible
  through existing contract diagnostics.
- Startup performs metadata discovery for registered or route-declared
  templates even when debug checks are disabled; loader-wide inventory remains
  in the dead-template checker until that rule migrates.
- Public graph compatibility remains intentionally undefined until a separate
  design review.
