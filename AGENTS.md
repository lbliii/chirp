<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Agent Constitution — Chirp

Ordinary work: use this root map plus only scoped maps on the target path.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Pillars

- Chirp is hypermedia-native: typed return values connect server-rendered HTML to browser behavior without a parallel SPA or JSON architecture.
- One template with named blocks serves full pages, htmx fragments, OOB updates, Suspense chunks, streaming HTML, and SSE payloads.
- The public `from chirp import ...` surface, AppConfig, CLI, docs, examples, scaffolds, tests, and changelog move together.
- Visible HTML corruption fails loud through rendering errors, app.check(), focused contract tests, and actionable diagnostics.
- Optional extras remain optional, and shared runtime state is frozen, request-scoped, single-owner, or explicitly lock-guarded for free-threaded Python.

## Search Discipline

- At task start, read the root map before repository discovery; never locate instructions by inventorying every AGENTS.md in the repository.
- Before reading or searching content beneath a path, open the nearest scoped map on that path; add another map only when the investigation crosses into its scope.
- If the request names an exact file and symbol or link, inspect that target before searching elsewhere.
- Search progressively: likely files, then filename or import discovery, then scoped content search; expand repository-wide only when scoped evidence fails or proves a cross-cutting dependency, and state the reason.
- Treat 10 commands or 12 content-exposed files as a strategy checkpoint, never as a hard stopping limit.
- For import, dependency, registration, or call-chain bugs, prove graph closure with a bounded static traversal: inspect ancestor package initializers, the target's module-level imports, and recursively only repository-local modules imported at module scope.
- During graph traversal, stop at function and class bodies, TYPE_CHECKING blocks, and classified external dependencies; inspect callers and tests only after the import graph closes and only to verify the named public entry point.
- Do not use repository-wide symbol, dependency, lockfile, documentation, or CI searches to establish import closure; a search budget cannot replace the bounded proof.

## Operating Rules

- Do not take, implement, close, or batch-plan issues labeled `good first issue` or titled `[GF]`; they are reserved for external contributors.
- The live GitHub issue graph is authoritative for active work, hierarchy, and blockers; roadmap prose, labels, markdown checklists, branches, and PR mentions do not replace native parent/sub-issue relationships.
- For maintainer selection use `scripts/backlog.py next` and `scripts/backlog.py explain N`; selection is read-only, `ready` is leaf-only, and every unblocked parent reaches a ready leaf.
- Backlog triggers retain their meaning: survey is read-only; next recommends; groom reconciles; cut decomposes into native sub-issues; reconcile verifies shipped behavior before closing.
- `ask stewards`, `bugbash`, `review swarm`, `steward synthesis`, `audit docs`, `content audit`, and `accuracy pass` are explicit review triggers: open the protocol, consult independent affected maps, preserve dissent, and synthesize with evidence.
- Behavioral issue closure needs `@pytest.mark.issue(N)` traceability or an explicit `Acceptance #N: n/a (<reason>)` receipt.
- Generated output under `site/public/` and `site/.bengal/` is not source-of-truth; edit source content/config and build or record a no-build rationale.
- Before finalizing agent-authored public files, remove customer names, private people or project names, private quotes, endpoints, and internal scale or cost figures.
- For htmx, OOB, Suspense, SSE, or shell failures, use Chirp DevTools (`debug=True`, Ctrl+Shift+D, `window.ChirpHtmxDebug`) before guessing.
- No silent except, unexplained type-ignore, vague error, speculative config, undocumented public behavior, or adjacent refactor unless it is the fix.

## Network

| Steward | Map | Invariants | Automated backing |
| --- | --- | --- | --- |
| ai | `src/chirp/ai/AGENTS.md` | 1 | 100% |
| app | `src/chirp/app/AGENTS.md` | 2 | 50% |
| benchmarks | `benchmarks/AGENTS.md` | 1 | 100% |
| cache | `src/chirp/cache/AGENTS.md` | 1 | 100% |
| changelog | `changelog.d/AGENTS.md` | 1 | 100% |
| cli | `src/chirp/cli/AGENTS.md` | 1 | 100% |
| contract_tests | `tests/contracts/AGENTS.md` | 1 | 100% |
| contracts | `src/chirp/contracts/AGENTS.md` | 2 | 50% |
| data | `src/chirp/data/AGENTS.md` | 1 | 100% |
| docs | `docs/AGENTS.md` | 1 | 100% |
| docs_tooling | `src/chirp/docs/AGENTS.md` | 1 | 100% |
| examples | `examples/AGENTS.md` | 1 | 100% |
| ext | `src/chirp/ext/AGENTS.md` | 1 | 100% |
| http | `src/chirp/http/AGENTS.md` | 1 | 100% |
| i18n | `src/chirp/i18n/AGENTS.md` | 1 | 100% |
| internal | `src/chirp/_internal/AGENTS.md` | 1 | 100% |
| markdown | `src/chirp/markdown/AGENTS.md` | 1 | 100% |
| middleware | `src/chirp/middleware/AGENTS.md` | 1 | 100% |
| pages | `src/chirp/pages/AGENTS.md` | 1 | 100% |
| pelt | `src/chirp/data/drivers/_pelt/AGENTS.md` | 2 | 50% |
| plan | `plan/AGENTS.md` | 2 | 0% |
| public | `src/chirp/AGENTS.md` | 3 | 66% |
| realtime | `src/chirp/realtime/AGENTS.md` | 1 | 100% |
| root | `AGENTS.md` | 7 | 85% |
| routing | `src/chirp/routing/AGENTS.md` | 1 | 100% |
| security | `src/chirp/security/AGENTS.md` | 3 | 33% |
| server | `src/chirp/server/AGENTS.md` | 2 | 50% |
| settings | `src/chirp/settings/AGENTS.md` | 1 | 100% |
| site | `site/AGENTS.md` | 1 | 100% |
| skill | `src/chirp/skill/AGENTS.md` | 1 | 100% |
| templating | `src/chirp/templating/AGENTS.md` | 2 | 50% |
| testing | `src/chirp/testing/AGENTS.md` | 1 | 100% |
| tests | `tests/AGENTS.md` | 1 | 100% |
| tools | `src/chirp/tools/AGENTS.md` | 1 | 100% |
| validation | `src/chirp/validation/AGENTS.md` | 1 | 100% |

## Protects (constitution)

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| The blessed public imports remain lazy, classified, and documented. | P0 | machine-backed | `uv run pytest tests/test_lazy_imports.py tests/test_public_api_docs.py -q` (`public-contract`) |
| app.check() contract rules retain end-to-end broken-app coverage. | P0 | machine-backed | `uv run pytest tests/contracts -q` (`contract-suite`) |
| The shipped source tree remains clean under Chirp's Python 3.14 Ty contract. | P1 | machine-backed | `uv run ty check src/chirp/` (`ty`) |
| Generated maps fail validation when stale, evidence-rotted, uncovered, over budget, or falsely wired to checks. | P1 | machine-backed | `uv run pytest tests/stewards -q` (`steward-tools`) |
| Repository source, tests, examples, scripts, and governance tooling remain Ruff-clean. | P1 | machine-backed | `uv run ruff check .` (`ruff`) |
| Repository Python formatting remains stable under Ruff. | P1 | machine-backed | `uv run ruff format . --check` (`format`) |
| Typed return values and named blocks remain the architecture rather than a parallel SPA or JSON response layer. | P0 | manual | README.md · `one-template/named-block render surface` |

## Stop & Ask

- A change alters public API, return-type semantics, AppConfig, protocol shapes, CLI commands, scaffold defaults, optional extras, or compatibility tiers.
- A change touches render plans, return types, OOB or Suspense block discovery, ancestor pruning, or BlockNotFoundError propagation.
- A change alters app.check() severity or default contract semantics, security/auth payloads, cache keys, schema or migration output, lifecycle publication, or free-threading assumptions.
- A sync fast-path change lacks a measurement plan, a bug cannot be reproduced, or test and code disagree.
- When a public-contract change depends on unresolved product or API choices, identify only the minimum blocking decisions and stop before designing the API or its documentation, examples, scaffolds, benchmarks, and release collateral.
- An irreversible operation, deletion, external write, or maintainer-only backlog decision is required.

## Done Criteria

- Run `uv run ruff check .` and `uv run ruff format . --check` (or record a justified narrower docs-only check).
- Run `uv run ty check src/chirp/` when Python source or public typing changes.
- Run the narrowest relevant pytest targets first and `uv run pytest` for release-class changes; code coverage remains at least 80 percent.
- Hypermedia changes include realistic tests for htmx and plain requests, missing blocks, sync and async paths, malformed forms, environment posture, and optional dependencies where relevant.
- Public behavior moves with docs, examples, scaffolds/templates, benchmarks or no-impact rationale, and a changelog fragment when required.
- Every accepted steward finding names proof and collateral or an explicit no-impact reason; user-facing errors name the surface to fix.

---

Explicit review/audit only: [.stewards/PROTOCOL.md](.stewards/PROTOCOL.md). Steward maintenance only: [.stewards/manifest.toml](.stewards/manifest.toml), then `python .stewards/verify.py --coverage`.
