# Chirp Agent Constitution

## North Star

Chirp exists to prove that Python apps can stay hypermedia-native: the server renders HTML, the browser renders UI, and typed return values connect the two without an SPA, JSON serialization layer, or JavaScript build pipeline. A single template with named blocks must safely serve full pages, htmx fragments, Suspense chunks, streaming HTML, and SSE payloads.

## Non-Negotiables

- The return type is the architecture. `Page`, `Fragment`, `OOB`, `Suspense`, `EventStream`, `ValidationError`, `FormAction`, `MutationResult`, `Action`, `Stream`, and `Redirect` drive negotiation, status, htmx awareness, and rendering.
- Use the right streaming type: `Stream` for progressive first-byte HTML, `Suspense` for initial shell-plus-deferred OOB blocks, `EventStream` for post-load SSE updates.
- One template, many access patterns. Named blocks are the unit; do not split a parallel partials or API serialization system.
- Frozen/slotted dataclasses are the default for config, return types, validation results, freeze results, and registry entries. Shared mutability needs an explicit lock or lifecycle boundary.
- `app.check()` is part of the product. New render wiring needs a startup contract that catches wrong usage before users see broken HTML.
- Fail loud. Missing OOB blocks raise `BlockNotFoundError`; orphan non-optional registry entries are ERROR; silent empty swaps are trust bugs.
- Layouts use composition, not page-template inheritance. Pages render into the layout content block via `render_with_blocks`; they do not override sibling layout blocks.
- Debug with Chirp DevTools before guessing at htmx/OOB/Suspense/SSE behavior: run with `debug=True`, open the app, press `Ctrl+Shift+D`, then inspect `window.ChirpHtmxDebug`.
- No silent `except`, unexplained `# type: ignore`, vague errors, or speculative config.

## Architecture Boundaries

- Public surface: `src/chirp/__init__.py`, `AppConfig`, top-level errors, plugins, context helpers, and stable/provisional names documented in `docs/public-api.md`.
- App lifecycle: registration, freeze, runtime publication, service injection, mounting, URL generation, and worker/lifespan hooks live under `src/chirp/app/`.
- HTTP primitives: immutable request/response/headers/cookies/query/forms and sync request types live under `src/chirp/http/`.
- Routing: path matching, params, named routes, and URL generation live under `src/chirp/routing/`; filesystem page discovery lives under `src/chirp/pages/`.
- Request handling: ASGI, negotiation, htmx awareness, fragment dispatch, debug pages, sender behavior, sync fast path, and dev server live under `src/chirp/server/`.
- Rendering: return types, Kida integration, render plans, fragments, OOB regions, navigation swaps, `Stream`, and `Suspense` live under `src/chirp/templating/`.
- Contract checks: `app.check()` categories, severities, snapshots, template scans, and custom check protocols live under `src/chirp/contracts/`.
- Middleware/security/cache/data/realtime/tools/validation/docs tooling are separate public or optional surfaces; keep their dependencies optional unless the project deliberately changes that contract.
- Docs, examples, scaffolds, tests, benchmarks, and release notes are collateral surfaces. User-facing behavior is incomplete until they agree.

## Stakes

- Return-type regressions send full documents into fragment targets, choose wrong status codes, or bypass htmx negotiation.
- OOB/Suspense regressions wipe visible DOM, leave deferred blocks unresolved, or target non-existent IDs without a useful error.
- SSE regressions silently close long-lived dashboards or widen per-event failures into stream failures.
- Free-threaded races corrupt shared registries, middleware state, context, cache, or reactive buses under Python 3.14t.
- `app.check()` regressions remove the only startup warning many app authors get before broken hypermedia ships.
- `chirp freeze` regressions break static docs and customer sites through bad links, missing search metadata, or wrong relative URLs.
- Scaffold/example drift teaches unsafe patterns that real users copy.

## Stop And Ask

Check in before:

- Changing public API, protocol shapes, return-type semantics, top-level exports, plugin protocols, CLI commands, or scaffold defaults.
- Adding a return type, `AppConfig` field, mandatory runtime dependency, optional extra, migration surface, release/build surface, or public config flag.
- Touching the render pipeline: `templating/render_plan.py`, `templating/returns.py`, Suspense block discovery, ancestor pruning, or `BlockNotFoundError` propagation.
- Promoting/demoting `app.check()` severities or changing default contract semantics.
- Changing data models, schema/migration output, cache key semantics, auth/security behavior, lifecycle/freeze behavior, or free-threaded shared state.
- Touching the sync fast path (`App.handle_sync`, `SyncRequest`, pre-encoded content types) without a measurement plan.
- Performing irreversible operations, deleting dead-looking code, or resolving test/code disagreement.
- Fixing a bug you cannot reproduce; ask for a minimal repro or environment dump.

## Anti-Patterns

- Adding `make_response()`, `jsonify()`, `to_json()`, or a REST-style side channel to solve a hypermedia return-type problem.
- Using `{% if key %}` for Suspense deferred values. Use `{% if key is not none %}` or `"key" in __chirp_defer_pending__`.
- Using bare jsDelivr package URLs for Alpine/plugins. Use explicit `/dist/cdn.min.js`.
- Setting `optional=True` on an OOB region to hide a typo.
- Mutating registries after freeze.
- Putting route dispatch, rendering, app lifecycle, and middleware concerns in one package because it is convenient.
- Refactoring adjacent issues during a bug fix unless the refactor is the fix.
- Adding parens to Python 3.14 multi-exception syntax that Ruff normalizes as `except ValueError, TypeError:`.

## Steward System

Agents read this root file plus the closest scoped `AGENTS.md` for every file they edit. Root is the constitution, routing guide, and swarm protocol; scoped files are domain stewards.

Scoped stewards own local invariants, refusal patterns, docs, tests, examples, fixtures, generated artifacts, and maintenance checks. They advocate for their domain, serve upstream/downstream peers with clearer contracts and diagnostics, and protect concrete quality bars. Cross-boundary work needs **Steward Notes** in the PR description naming consulted files, accepted/deferred findings, required proof, collateral updates, and dissent.

Every steward uses this operating model:

- Point Of View: who or what the domain represents.
- Protect: invariants, contracts, quality bars, and failure modes.
- Contract Checklist: concrete surfaces to inspect when this domain changes.
- Advocate: features, fixes, and investments this domain should push for.
- Serve Peers: upstream/downstream domains needing clearer contracts, diagnostics, docs, tests, or ergonomics.
- Do Not: local anti-patterns.
- Own: tests, docs, examples, fixtures, checks, and maintenance chores.

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
| Validation rules and form-result contracts | `src/chirp/validation/AGENTS.md` |
| Docs tooling, autodoc, search, docs plugin | `src/chirp/docs/AGENTS.md` |
| Markdown optional extra | `src/chirp/markdown/AGENTS.md` |
| i18n optional surface | `src/chirp/i18n/AGENTS.md` |
| AI/LLM optional extra | `src/chirp/ai/AGENTS.md` |
| Extension adapters, especially chirp-ui | `src/chirp/ext/AGENTS.md` |
| MCP/tools integration | `src/chirp/tools/AGENTS.md` |
| CLI and scaffolds | `src/chirp/cli/AGENTS.md` |
| Test helpers | `src/chirp/testing/AGENTS.md` |
| Test suite ownership | `tests/AGENTS.md` |
| Contract test suite ownership | `tests/contracts/AGENTS.md` |
| Examples as executable docs | `examples/AGENTS.md` |
| Narrative docs and release policy | `docs/AGENTS.md` |
| Changelog fragments and release-note inputs | `changelog.d/AGENTS.md` |
| Planning and roadmap artifacts | `plan/AGENTS.md` |
| Bengal docs site content/config | `site/AGENTS.md` |
| Benchmarks and performance claims | `benchmarks/AGENTS.md` |

## Contract Checklist

For cross-surface changes, identify every surface that should agree: CLI/API, programmatic use, protocol, schema/types, UI, docs, examples, scaffold/templates, tests, benchmarks, and changelog.

Every accepted finding must name required proof and collateral updates, or explicitly say `no collateral: <reason>`. Docs/examples/scaffold move in the same PR as user-facing behavior unless synthesis records why they are unaffected. Contract-affecting PRs include a parity matrix when behavior spans multiple entrypoints.

## Steward Signal Format

Steward findings should be contract-oriented, evidence-backed, and collateral-aware.

- Steward:
- Area:
- Severity: P0/P1/P2/P3
- Invariant:
- Evidence:
- User Impact:
- Required Fix:
- Required Proof:
- Collateral:
- Confidence:

## Steward Swarms

When the user asks for `ask stewards`, `bugbash`, `review swarm`, or `steward synthesis`, and delegation is available:

- Spawn independent steward agents for affected domains.
- Each steward reads root plus its closest scoped `AGENTS.md`.
- Each steward advocates only for that domain's interests.
- Each steward returns findings in the Steward Signal Format.
- The implementing agent owns synthesis and final decisions.
- Stewards advise and create useful tension; they do not own the integrated implementation.
- Keep PR scope bounded to accepted findings and their proof/collateral.
- Defer unrelated steward suggestions to not-now/follow-up.

For backlog, roadmap, or prioritization work, consult all scoped stewards and produce raw steward signals, confidence, dependencies, risks, convergence, minority reports, ranked backlog, and not-now items.

## Steward Feedback Loop

- Steward miss: when a bug escapes an applicable steward, update the checklist, add a regression test, add a docs/snippet check, refine routing, or record why the miss should not become policy.
- Steward overreach: when a steward repeatedly pulls unrelated work into PRs, narrow the checklist, split the steward, or move the concern to follow-up.
- Repeated high-quality findings should become checklist items.
- Repeated noisy findings should be pruned or clarified.
- Steward guidance evolves from escaped bugs, late collateral updates, CI/review misses, and recurring review comments.

## When To Consult

- Proactively consult stewards for cross-boundary, public-facing, hard-to-reverse, performance-sensitive, concurrency-sensitive, security-sensitive, or contract-affecting work.
- Use the nearest steward for local work.
- Use multiple stewards when ownership lines cross.
- Parallelize steward consultation only when questions are independent.
- Keep final synthesis and implementation accountability with the implementing agent.

## Ask Stewards

Trigger phrase: `ask stewards`.

For implementation work, consult affected stewards and return synthesis before or during the change. Include accepted/deferred findings, merged duplicates, minority reports, required proof, collateral updates, and not-now items.

For multi-surface work, include a parity matrix like:

| Contract | API/CLI | Programmatic | Protocol | Schema/Types | Docs | Examples | Tests |
| --- | --- | --- | --- | --- | --- | --- | --- |

## Extension Routing

- Chirp plugin protocols and app registration live in `src/chirp/plugin.py`, `src/chirp/app/`, and `src/chirp/contracts/`.
- MCP/tool extensions live under `src/chirp/tools/`.
- chirp-ui integration lives in `src/chirp/ext/chirp_ui.py` and related template/filter contracts.
- Optional extras are routed by package: `forms`, `sessions`, `auth`, `markdown`, `ui`, `redis`, `data-pg`, `ai`, and `config`.

## Done Criteria

- `uv run ruff check .` and `uv run ruff format . --check` clean; no new unexplained `# type: ignore` or `# noqa: S110`.
- `uv run ty check src/chirp/` clean when Python code or public typing changes.
- `uv run pytest` passes for release-class changes; use the narrowest relevant subsets first while developing. Coverage stays at or above 80 percent.
- Hypermedia surface changes include end-to-end `tests/contracts/` coverage through `TestClient` or `app.check()`.
- Tests exercise the interesting path: htmx vs non-htmx, missing block, awaitable vs sync context, malformed form, production vs debug where relevant.
- Public API changes include a towncrier fragment in `changelog.d/` and migration notes if behavior breaks.
- Docs/changelog/migration notes, examples/scaffold/templates, benchmarks, and performance/concurrency/security notes move with the behavior where relevant.
- Every accepted steward finding has test/docs/example/benchmark proof or an explicit no-impact note.
- Error messages name what to fix: template, block, route, selector, registration, config flag, or import string.

## Review Notes

- Commit/PR titles usually use `feat:`, `fix:`, `refactor:`, `build:`, or `deps:` in imperative voice, but PR clarity matters more than prefix.
- Keep one concern per PR unless a concept rename across many files is the safer review unit.
- Flag surprises: weird tests, unused public names, suppressions, dead-looking code, benchmark gaps, free-threading assumptions, steward disagreement, and deferred/not-now findings.
- Put the why in the PR description. Let the diff show the what.

## When This File Is Wrong

Update it. Root and scoped `AGENTS.md` files are first-class project artifacts; they should evolve when evidence proves the current guidance misses real failures or creates noise.
