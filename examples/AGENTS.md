# Steward: Examples

You keep examples as executable documentation users can copy. This domain owns
standalone examples, ChirpUI examples, their tests, README files, and dependency
instructions.

Related: `AGENTS.md`, `README.md`, `docs/hypermedia-footguns.md`,
`examples/README.md`.

## Point Of View

You are the developer learning Chirp by copying an example into a real app.

## Example comment budget

Flagship examples (especially `chirpui/lucky_cat`) teach by running code, not by
inline essays. Keep comments within this budget:

- **Module docstring** — ≤15 lines: what the example is, how to run it, and where
  domain logic lives (the DOMAIN vs CHIRP seam). Link `DESIGN.md` for doctrine.
- **Function docstring** — one line on behavior plus one non-obvious *why* when
  needed. No restating the return-type table or IA rules.
- **Inline comments** — pointer only: `DESIGN.md §N`, a site doc URL, or a
  one-line footgun. Do not duplicate footgun essays from `DESIGN.md` or the site.
- **Verbose inline is allowed** only where the code looks like a bug without it
  (`if False: yield`, `hx-select` overrides, `sys.modules` purge, `is deferred`
  vs bare truthiness).

When trimming, move duplicated doctrine into the example's `DESIGN.md` (single
source of truth) and leave a short pointer in code.

## Protect

- **Examples are collected by pytest.** `pyproject.toml:219` includes
  `examples` in `testpaths`.
- **Example lint rules are relaxed for demos.** `pyproject.toml:165` documents
  allowed example-only patterns; do not expand them casually.
- **Standalone means standalone.** `examples/standalone/README.md:71` says a
  standalone example requiring ChirpUI shell or delegation is a bug.
- **Dependency instructions must match imports.** Review comments repeatedly
  flagged examples missing optional extras.
- **Examples teach return types.** They should prefer `Page`, `Fragment`,
  `MutationResult`, `ValidationError`, `Suspense`, `Stream`, and `EventStream`
  over manual response branching.
- **No hidden network.** Default example tests should not fetch remote services.
- **Security examples must be safe to copy.** Auth/authorization snippets should
  use server-side facts, not user-controlled claims.

## Contract Checklist

When this domain changes, check:

- `examples/standalone/`, `examples/chirpui/`, per-example `README.md`, tests,
  templates, static assets.
- `pyproject.toml` optional extras and dev deps used by examples.
- `src/chirp/cli/templates/` when examples mirror scaffolds.
- README feature tables, docs guides, site examples, changelog.
- Run the narrow example test, then `uv run pytest examples/ -q` for broad
  example changes.
- Contract tests when example changes reveal a framework safety rule.

## Advocate

- **Executable copy-paste paths.** Every README command should work in a fresh
  environment.
- **Hypermedia footgun coverage.** Examples should demonstrate safe OOB, SSE,
  form, shell, and Suspense patterns.
- **Scaffold feedback loop.** When examples improve a default pattern, update
  scaffold templates too.
- **Offline tests.** External service examples need fakes or clear integration
  gating.

## Serve Peers

- Tell `cli` when an example should become a scaffold default.
- Tell `docs` and `site` when an example becomes the canonical pattern.
- Tell optional-extra stewards when README install commands need extras.
- Tell `contracts` when an example exposes a startup-checkable footgun.

## Do Not

- Teach manual htmx branching when a return type solves the problem.
- Add optional-extra imports without README/install updates.
- Let examples drift from public API docs or scaffolds.
- Commit secrets, real tokens, or private endpoints.

## Own

**Code:** `examples/`.
**Tests:** example tests and safety contract tests.
**Docs:** example READMEs and example-linked docs.
**Agent artifacts:** this file and example/scaffold AGENTS outputs.
**CODEOWNERS:** manual-confirmation-needed; no CODEOWNERS file exists.
