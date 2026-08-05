# Decision — 2026-08-05

**Status:** proposed (awaiting maintainer approval)

**Issue:** [#908](https://github.com/lbliii/chirp/issues/908)

**Parent epic:** [#899](https://github.com/lbliii/chirp/issues/899)

**Parent saga:** [#896](https://github.com/lbliii/chirp/issues/896)

**Evidence:** Surveyed `pyproject.toml` (`[project.dependencies]`,
`[project.optional-dependencies]`, `[dependency-groups]`),
`.github/workflows/{ci,benchmarks,pages,python-publish,contract-diff}.yml`,
`site/content/docs/get-started/installation.md`, `CONTRIBUTING.md`,
`benchmarks/README.md`, and the local `uv.lock` resolution path for the
benchmark extra (APSW via `python-fasthtml` → `fastlite` → `apswutils` →
`apsw`).

---

## Decision

Chirp supports a **finite, named set of dependency resolution profiles**.
Each profile has one purpose, one canonical install command, one import
smoke, one CI ownership lane (or an explicit “gap owned by #910/#911”),
and one release expectation. Profiles are **not** a Cartesian product of
extras × groups × Python builds.

### Non-negotiable policy

1. **Minimal stays minimal.** Optional extras and dependency groups are
   never pulled into the default `bengal-chirp` install. No new runtime
   dependency may be added to `[project.dependencies]` under #899.
2. **Optional stays optional.** A profile that needs an extra installs
   that extra explicitly (`--extra NAME` / `bengal-chirp[NAME]`).
3. **Unsupported combinations are unsupported.** Combining arbitrary
   extras, mixing `benchmark` with docs, or inventing ad-hoc
   `uv pip install` overlays is allowed for local experimentation but
   is **not** a supported profile and does not get CI or release
   receipts unless promoted by a new decision issue.
4. **Adding a profile requires a decision leaf.** New profiles need an
   explicit decision (purpose, command, smoke, CI lane, release
   expectation) plus follow-on implementation issues. Do not expand the
   matrix in implementation PRs alone.
5. **Public install defaults do not change in this decision.** Renaming,
   merging, or broadening extras (`all`/`full`, floor bumps, moving
   packages into core) requires a separate approved implementation
   issue after this matrix is accepted.

### Supported profiles

Canonical consumer commands use the published package name
`bengal-chirp`. Repository development commands use `uv sync` against
this checkout. Both forms resolve the same declared extras/groups.

| Profile ID | Purpose | Canonical install | Import smoke (proposed for #910) | CI lane today | Release expectation | Owner |
| --- | --- | --- | --- | --- | --- | --- |
| `minimal` | End-user core framework only | `uv add bengal-chirp` / `pip install bengal-chirp` | `import chirp; chirp.__version__` | **Gap** — no fresh-env job yet | Wheel installs with only declared core deps (`kida-templates`, `anyio`, `bengal-pounce`, `milo-cli`) | #910 / #911 |
| `dev` | Ordinary contributor + default CI | `uv sync --group dev` | `import chirp, pytest, httpx, multipart, itsdangerous, patitas, chirp_ui` | `ci.yml` → `ruff`, `ty`, `test` | Default contributor path; lock/group must resolve clean | #910 / #911 / #916 |
| `docs` | Bengal docs site build | `uv sync --group docs` | `import bengal, chirp_ui` | `pages.yml` → `build` | Docs deploy must resolve without yanked packages | #910 / #911 / #916 |
| `browser` | Playwright browser smoke | `uv sync --group dev --group browser` | `import playwright` (+ Chromium install) | `ci.yml` → `browser-smoke` | Browser lane remains isolated; not part of minimal/dev default | #910 / #911 |
| `benchmark` | Framework comparison suite | `uv sync --extra benchmark` | `import fastapi, flask, starlette, litestar, httpx` (and FastHTML stack when exercised) | `benchmarks.yml` (core/pelt jobs use `dev` / `dev+data-pg`; networked comparison uses this extra) | Advisory perf evidence; **must not** yank-warn on refresh once #911 gates it | #910 / #911 / #916 |
| `full` | Aggregate “common optional stack” alias | `uv add "bengal-chirp[full]"` / `pip install "bengal-chirp[full]"` | Same as composing `forms`+`sessions`+`auth`+`testing`+`markdown` smokes | **Gap** — no dedicated job | Resolves exactly the packages listed under `full` in `pyproject.toml`; does **not** imply `ui`, `passkeys`, `config`, `redis`, `ai-bedrock`, or `benchmark` | #910 / #911 |
| `all` | Documented synonym of `full` (identical contents today) | `uv add "bengal-chirp[all]"` | Same as `full` | **Gap** — treated as alias of `full` | Must remain content-identical to `full` until a separate issue deliberately diverges or deletes one alias | #910 / #911 |
| `extra-forms` | Multipart form parsing | `uv add "bengal-chirp[forms]"` | `import multipart` | Covered transitively by `dev`; isolated fresh-env **gap** | Optional capability remains opt-in | #910 / #911 |
| `extra-sessions` | Signed cookie sessions | `uv add "bengal-chirp[sessions]"` | `import itsdangerous` | Covered transitively by `dev`; isolated fresh-env **gap** | Optional capability remains opt-in | #910 / #911 |
| `extra-auth` | Argon2 password hashing | `uv add "bengal-chirp[auth]"` | `import argon2` | Covered transitively by `dev`; isolated fresh-env **gap** | Optional capability remains opt-in | #910 / #911 |
| `extra-passkeys` | WebAuthn / passkeys | `uv add "bengal-chirp[passkeys]"` | `import webauthn` | Covered transitively by `dev` (group lists `webauthn`); isolated fresh-env **gap** | Deliberately **not** in `all`/`full` (heavy cryptography stack) | #910 / #911 |
| `extra-testing` | httpx test-client transport | `uv add "bengal-chirp[testing]"` | `import httpx` | Covered by `dev` / `test`; isolated fresh-env **gap** | Optional for end users; present in contributor `dev` | #910 / #911 |
| `extra-data-pg` | PostgreSQL via in-tree pelt (no PyPI deps) | `uv add "bengal-chirp[data-pg]"` / `uv sync --group dev --extra data-pg` | `import chirp.data.drivers._pelt` | `ci.yml` → `test-postgres`, `data-pg-gil-gate`; `benchmarks.yml` → `pelt-controlled-evidence` | Extra remains empty of third-party deps; capability is import/behavioral | #910 / #911 |
| `extra-ai` | LLM streaming over raw HTTP | `uv add "bengal-chirp[ai]"` | `import httpx`; `import chirp.ai` | **Gap** — no dedicated optional-AI lane | Optional; shares `httpx` with `testing`/`ai` | #910 / #911 |
| `extra-ai-bedrock` | AWS Bedrock signing | `uv add "bengal-chirp[ai-bedrock]"` | `import botocore, httpx` | **Gap** | Optional; not in `all`/`full` | #910 / #911 |
| `extra-markdown` | Patitas markdown rendering | `uv add "bengal-chirp[markdown]"` | `import patitas` | Covered transitively by `dev`; isolated fresh-env **gap** | Optional; in `all`/`full` | #910 / #911 |
| `extra-ui` | Install chirp-ui via Chirp extra | `uv add "bengal-chirp[ui]"` | `import chirp_ui` | Partial — `contract-diff.yml`; `chirp-ui-compat` uses `--extra ui` | Peer package; floor is `chirp-ui>=0.11.4` in `pyproject.toml` | #910 / #911 |
| `extra-config` | python-dotenv for `AppConfig.from_env()` | `uv add "bengal-chirp[config]"` | `import dotenv` | **Gap** | Optional; not in `all`/`full` | #910 / #911 |
| `extra-redis` | Redis sessions / rate limit / signal backplane | `uv add "bengal-chirp[redis]"` | `import redis` | **Gap** | Optional; not in `all`/`full` | #910 / #911 |
| `chirp-ui-compat` | Cross-version Chirp ↔ chirp-ui compatibility | `uv sync --group dev --extra ui` then pin `chirp-ui==0.10.0` **or** upgrade to latest (as CI does) | `import chirp_ui` + `tests/test_chirpui_boundary.py` / compat suite | `ci.yml` → `chirp-ui-compat` (matrix: `0.10.0`, `latest`) | Compatibility lane only; not a default install; retain/remove owned by saga #896 / epic #897 | #910 / #911 |

### Profiles explicitly out of the supported matrix

These exist in CI or local practice but are **not** promoted to supported
dependency-resolution profiles by this decision:

| Ad-hoc overlay | Why unsupported as a profile |
| --- | --- |
| `query-interop` (`dev` + `uv pip install "bengal-pounce[h2,h3]==…" "httpx[http2]…" "uvicorn==…"`) | Protocol-interop proof overlay, not a declared extra/group |
| Furatena canary (`uv sync --locked --all-groups` in a foreign repo + candidate wheel) | Downstream advisory release check owned by publish workflow, not a Chirp install profile |
| `browser-smoke` pin of `chirp-ui==0.10.0` after sync | Compatibility floor overlay for Lucky Cat smoke; owned by `chirp-ui-compat` / browser lane receipts, not a distinct install profile |
| Arbitrary comma-combinations of extras beyond `all`/`full` | Supported only as user composition; each named `extra-*` is verified alone |

### Ownership of follow-on implementation

| Issue | Consumes this matrix how |
| --- | --- |
| [#910](https://github.com/lbliii/chirp/issues/910) | Implements fresh-environment install + import smoke for every Supported profile row; reports failing profile ID and resolution path |
| [#911](https://github.com/lbliii/chirp/issues/911) | Gates yanked packages and unsatisfied resolution for Supported profiles (especially `benchmark` / APSW transitive path) |
| [#916](https://github.com/lbliii/chirp/issues/916) | Bounded lock/ecosystem refresh receipts name affected Supported profiles |
| [#918](https://github.com/lbliii/chirp/issues/918) | Warning budget allowlist is keyed by profile (or explicit “core/dev default”) with owner + expiry |

**Implementation owner for this decision’s consumption:** #910 (primary),
with #911 / #916 / #918 as dependent gates. This decision issue itself
ships **policy + matrix collateral only**.

### Release expectation (summary)

- **Block release** when `minimal`, `dev`, `docs`, `browser`,
  `extra-data-pg`, or `chirp-ui-compat` cannot resolve/install/smoke
  once #910/#911 land.
- **Block or bound** `benchmark` when yanked transitive packages appear
  (current known debt: APSW 3.53.3.0 via FastHTML stack) — receipt via
  #911/#916, not silent ignore.
- **Do not block core release** solely because an unsupported ad-hoc
  overlay (query-interop pins, Furatena) fails — those remain advisory
  or isolated lanes unless separately promoted.

---

## Rejected alternatives

1. **Cartesian matrix of every extra × group × Python build.** Rejected:
   unbounded CI cost and ambiguous ownership; epic #899 explicitly
   forbids this.
2. **Collapse all optional extras into `minimal` or `dev`.** Rejected:
   violates “optional extras remain optional” and the epic boundary
   against expanding the minimal install.
3. **Treat every CI job install line as a supported profile.** Rejected:
   overlays like query-interop and Furatena are proofs, not product
   install surfaces.
4. **Delete `all` or `full` in this decision.** Rejected: public install
   surface change; belongs to a separate approved implementation issue.
   This decision freezes them as synonyms with identical contents.
5. **Make `chirp-ui` part of `dev` the sole UI compatibility commitment.**
   Rejected: `dev` may install current `chirp-ui`, but cross-version
   compatibility is a distinct profile (`chirp-ui-compat`).

---

## Revisit trigger

Re-open or supersede this decision when any of the following occur:

- A new optional extra or dependency group is added to `pyproject.toml`.
- `all` and `full` diverge, or either gains `ui` / `passkeys` / `redis` /
  `config` / `ai-bedrock` / `benchmark`.
- Chirp UI is retained, removed, or re-homed under epic #897 in a way that
  invalidates `extra-ui` or `chirp-ui-compat`.
- Python requires-python or free-threading posture changes the smoke set.
- Maintainers want query-interop or Furatena promoted into the supported
  matrix.

---

## Survey notes (evidence detail)

### Declared surfaces (`pyproject.toml`)

- **Core:** `kida-templates`, `anyio`, `bengal-pounce`, `milo-cli`.
- **Extras:** `forms`, `sessions`, `auth`, `passkeys`, `testing`,
  `data-pg` (empty), `ai`, `ai-bedrock`, `markdown`, `ui`, `config`,
  `redis`, `all`, `benchmark`, `full`.
- **Groups:** `docs`, `dev`, `browser`.
- **`all` == `full` today** (forms, sessions, auth, httpx, markdown).
  Neither includes `passkeys`, `ui`, `config`, `redis`, `ai-bedrock`, or
  `benchmark`. Docs claim `all` includes `data-pg`; the extra is empty of
  third-party deps, so resolution is a no-op beyond capability marking.

### CI install map (as of survey)

| Workflow job | Install |
| --- | --- |
| `ci.yml` `ruff` / `ty` / `test` | `uv sync --no-sources --group dev` |
| `ci.yml` `browser-smoke` | `uv sync --no-sources --group dev --group browser` (+ Playwright Chromium; then pin `chirp-ui==0.10.0`) |
| `ci.yml` `query-interop` | `dev` + ad-hoc pounce/httpx/uvicorn pins |
| `ci.yml` `test-postgres` / `data-pg-gil-gate` | `uv sync --no-sources --group dev --extra data-pg` |
| `ci.yml` `chirp-ui-compat` | `uv sync --no-sources --group dev --extra ui` + version pin/upgrade |
| `contract-diff.yml` | `uv sync --no-sources --group dev --extra ui` |
| `pages.yml` | `uv sync --no-sources --group docs` |
| `benchmarks.yml` | `dev` or `dev --extra data-pg` (not `--extra benchmark`) |
| `python-publish.yml` Furatena canary | Foreign repo `uv sync --locked --all-groups` + candidate wheel |

### Known gaps this matrix exposes (for #910/#911/#916)

- No clean-environment smoke for `minimal`, most solitary `extra-*`
  profiles, `full`/`all`, `extra-ai`, `extra-ai-bedrock`, `extra-config`,
  or `extra-redis`.
- Networked framework comparison (`--extra benchmark`) is documented but
  not the default `benchmarks.yml` install line.
- Benchmark transitive APSW 3.53.3.0 is the concrete yanked-package debt
  named by epic #899.
- `browser-smoke` pins `chirp-ui==0.10.0` while the `ui` extra floor is
  `>=0.11.4` — compatibility posture lives in `chirp-ui-compat`, not in
  `extra-ui` alone.
