# Optional-capability proof matrix

Decision evidence for [#901](https://github.com/lbliii/chirp/issues/901)
(parent epic [#898](https://github.com/lbliii/chirp/issues/898), saga
[#896](https://github.com/lbliii/chirp/issues/896)), recorded 2026-08-05.

This ledger creates **no runtime, dependency, or CI behavior**. It is the
reviewable source of truth that later children (#906, #909, #915, #917, #926)
implement against.

## Decision — 2026-08-05

```text
Decision — 2026-08-05
Status: proposed (awaiting maintainer approval)
Evidence:
  - pyproject.toml [project.optional-dependencies] (15 named extras)
  - README.md Optional extras table; site/content/docs/get-started/installation.md
  - .github/workflows/ci.yml jobs; benchmarks.yml; contract-diff.yml
  - dependency-groups.dev packages installed by the default CI `test` job
  - skip/importorskip sites in tests/ for argon2, redis, botocore, chirp_ui, playwright
Decision:
  Adopt the matrix below as the authoritative map from every advertised
  optional extra to dependency profile, defining behavior, service/credential
  posture, tests, non-skipping CI lane, owner, and evidence receipt.
  Classify each row as already_proved, needs_lane, or n_a.
  Map open proof gaps to existing children #906/#909/#915/#917/#926 rather
  than duplicating scope. Preserve existing specialized lanes as cited
  evidence. Treat "proved" as: the named lane installs the dependency (or an
  equivalent documented profile), supplies required infrastructure, and runs
  the defining tests; skip-failure enforcement remains #917.
Rejected alternatives:
  - Treating dependency-groups.dev presence alone as permanent proof without
    naming a lane and owner (hides profile moves under #899/#897).
  - Requiring live third-party LLM/AWS credentials in pull-request CI.
  - Merging Redis/Argon2/provider proof into the default free-threaded unit job.
  - Creating new child issues that duplicate #906/#909/#915/#917/#926.
  - Changing CI or optional-extra installs as part of this decision PR.
Implementation owner: none (decision record); proof work #906 #909 #915 #917 #926
Revisit trigger:
  - Any new or renamed entry under [project.optional-dependencies]
  - Moving an optional package into/out of dependency-groups.dev
  - Adding/removing/renaming a specialized CI job that a matrix row cites
  - Closing #917 (skip-fail) or changing what "non-skipping" means
```

## Inventory authority

| Source | Role |
| --- | --- |
| `pyproject.toml` `[project.optional-dependencies]` | Canonical advertised extras |
| `README.md` Optional extras table | Public package advertisement |
| `site/content/docs/get-started/installation.md` | Install docs advertisement |
| `.github/workflows/ci.yml` | Primary PR CI lanes |
| `.github/workflows/benchmarks.yml` | Benchmark tooling lane |
| `.github/workflows/contract-diff.yml` | ChirpUI contract-diff lane |

### Advertising drift (receipt, not a docs rewrite)

| Extra in `pyproject.toml` | README | Installation docs |
| --- | --- | --- |
| `forms`, `sessions`, `auth`, `testing`, `data-pg`, `ai`, `markdown`, `ui`, `config`, `redis`, `all` | listed (except `all` shown as `all`/`full`) | listed |
| `passkeys` | listed | **missing** from extras dropdown |
| `ai-bedrock` | **missing** | **missing** |
| `benchmark` | **missing** | **missing** (tooling extra) |
| `full` | listed with `all` | listed via `all` row |

The matrix includes every `pyproject.toml` extra. Doc drift is owned by #926
when publishing evidence guidance; this decision does not rewrite install docs.

## Proof vocabulary

| Status | Meaning |
| --- | --- |
| `already_proved` | A named CI lane installs the dependency (or equivalent profile), supplies required services, and runs defining behavioral tests today. Skip-fail is enforced by #917 (`CHIRP_CAPABILITY_LANE`). |
| `needs_lane` | Advertised capability lacks a non-skipping CI path for its defining behavior (dependency absent, service absent, or only import/mock coverage where live behavior is advertised). |
| `n_a` | Not a product capability to prove as a unit (aggregate profile or tooling meta-extra); explicit rationale required. |

A **local skip is not a CI gap** when a named specialized lane already installs
the dependency and runs the tests. Conversely, presence in `dependency-groups.dev`
is only proof when the matrix names the job that uses that profile.

## Existing specialized lanes (preserve; do not duplicate)

| Lane | Workflow job | Install / infrastructure | Evidence role |
| --- | --- | --- | --- |
| Default unit | `ci.yml` → `test` | `uv sync --group dev` (free-threaded 3.14t) | Ordinary suite; currently also carries several optional packages via `dev` |
| Browser | `ci.yml` → `browser-smoke` | `--group browser` + Playwright Chromium | Real-browser smoke (not an optional-extra row) |
| Query interop | `ci.yml` → `query-interop` | protocol clients + nginx | RFC 10008 wire proof (not an optional-extra row) |
| Auth (Argon2) | `ci.yml` → `auth-capability` | `--extra auth` + `CHIRP_REQUIRE_ARGON2=1` + `CHIRP_CAPABILITY_LANE` | `auth` argon2id hash/verify/upgrade |
| Redis | `ci.yml` → `redis-capability` | `--extra redis` + Redis service + `CHIRP_REQUIRE_REDIS=1` + `CHIRP_CAPABILITY_LANE` | `redis` sessions / cache / rate-limit + outage |
| Config (dotenv) | `ci.yml` → `config-capability` | `--extra config` + `CHIRP_REQUIRE_DOTENV=1` + `CHIRP_CAPABILITY_LANE` | `config` `.env` load via `AppConfig.from_env` |
| AI Bedrock | `ci.yml` → `ai-bedrock-capability` | `--extra ai-bedrock` + `CHIRP_REQUIRE_BOTOCORE=1` + `CHIRP_CAPABILITY_LANE` | `ai-bedrock` SigV4 signing (mock transport; no AWS creds) |
| PostgreSQL matrix | `ci.yml` → `test-postgres` | `--extra data-pg` + Postgres 13–18 | `data-pg` live backend |
| Free-threaded PG | `ci.yml` → `data-pg-gil-gate` | `--extra data-pg` + Postgres 18 + `PYTHON_GIL=0` | `data-pg` concurrency |
| Chirp UI compat | `ci.yml` → `chirp-ui-compat` | `--extra ui` + version matrix | `ui` compatibility |
| Contract diff | `contract-diff.yml` | `--extra ui` | UI surface diff (supporting) |
| Benchmarks | `benchmarks.yml` | `--extra data-pg` / core bench deps; path-filtered | `benchmark` tooling |
| Passkeys (unit) | `ci.yml` → `test` | `webauthn` via `dependency-groups.dev` | `passkeys` ceremony unit tests |

## Default `dev` profile vs advertised extras

`uv sync --group dev` (default CI `test` / `ruff` / `ty`) installs these
optional packages **without** `--extra <name>`:

| Package | Related extras |
| --- | --- |
| `python-multipart` | `forms` |
| `itsdangerous` | `sessions` |
| `httpx` | `testing`, `ai` |
| `webauthn` | `passkeys` |
| `patitas[syntax]` | `markdown` |
| `chirp-ui` | `ui` |

**Not** installed by default `dev` (verified absent in an ordinary local
`uv sync --group dev` environment on 2026-08-05):

| Package | Related extras |
| --- | --- |
| `argon2-cffi` | `auth` |
| `redis` | `redis` |
| `python-dotenv` | `config` |
| `botocore` | `ai-bedrock` |
| Benchmark peer frameworks | `benchmark` |

## Capability matrix

| Extra | Deps | Defining behavior | Service / credentials | Defining tests (representative) | Non-skipping CI lane | Status | Owner steward | Evidence / gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `forms` | `python-multipart` | Multipart parse, upload caps, bomb guards | none | `tests/test_forms.py`, form integration | `ci.yml`/`test` via `dev` | `already_proved` | http / validation | Receipt: multipart in `dev`. #917 for skip-fail. |
| `sessions` | `itsdangerous` | Signed cookie sessions / middleware | none | `tests/test_sessions.py` (non-Redis) | `ci.yml`/`test` via `dev` | `already_proved` | middleware / security | Receipt: itsdangerous in `dev`. #917. |
| `auth` | `argon2-cffi` | argon2id hash/verify; upgrade path | none | `tests/test_passwords.py` Argon2 classes; `tests/contracts/test_password_extra.py` | `ci.yml` → `auth-capability` | `already_proved` | security | Lane installs `--extra auth`, asserts import, sets `CHIRP_REQUIRE_ARGON2=1` (#909) and `CHIRP_CAPABILITY_LANE=auth-capability` (#917). Default `dev` still omits argon2. |
| `passkeys` | `webauthn` (+ cryptography) | WebAuthn begin/finish ceremony | none for unit; browser authenticator for e2e | `tests/test_passkeys.py`; contracts `test_passkeys_rule.py`; opt-in `examples/standalone/passkeys_minimal` (`passkeys_e2e`) | `ci.yml`/`test` via `dev` (unit/contract) | `already_proved` (unit) | security | Browser e2e is local/opt-in, not PR CI — explicit N/A for PR credential/browser lane; do not fold into #906. #917. |
| `testing` | `httpx` | Test client transport | none | TestClient / httpx-backed suite | `ci.yml`/`test` via `dev` | `already_proved` | testing | Same httpx install as `ai`. #917. |
| `data-pg` | _(empty; in-tree pelt)_ | Live PostgreSQL round-trip, TLS/auth, jobs, GIL gate | Postgres service | `tests/test_pelt/*`, `tests/test_jobs_postgres.py`, schema introspect | `test-postgres` + `data-pg-gil-gate` | `already_proved` | data / pelt | Preserve 13–18 + free-threaded lanes. #917. |
| `ai` | `httpx` | LLM streaming over raw HTTP (mocked) | **no** live provider keys in PR CI | `tests/test_ai/*` (httpx importorskip) | `ci.yml`/`test` via `dev` | `already_proved` | ai | Live provider calls are N/A for PR CI (credential-safe). #917. |
| `ai-bedrock` | `botocore`, `httpx` | Bedrock signing / generate path | **no** AWS credentials in PR CI; fixture/monkeypatch only | `tests/test_ai_bedrock_capability.py`; `tests/test_ai/test_phase3.py::test_bedrock_generate_requires_botocore` | `ci.yml` → `ai-bedrock-capability` | `already_proved` | ai | Lane installs `--extra ai-bedrock`, asserts import, sets `CHIRP_REQUIRE_BOTOCORE=1` + `CHIRP_CAPABILITY_LANE=ai-bedrock-capability` (#915/#917). Default `dev` still omits botocore. |
| `markdown` | `patitas[syntax]` | Markdown render + highlighting filter | none | `tests/test_markdown.py` | `ci.yml`/`test` via `dev` | `already_proved` | markdown | Receipt: patitas in `dev`. #917. |
| `ui` | `chirp-ui` | Layout macros, CSS verify, shell examples | none | `tests/test_chirpui_*`, contracts ChirpUI rules, shell examples | `chirp-ui-compat` (+ `contract-diff.yml`) | `already_proved` | ext / site | Authoritative lane is `chirp-ui-compat`, not incidental `dev` install. #917; demotion work stays under #897. |
| `config` | `python-dotenv` | `AppConfig.from_env()` loads `.env` when installed | none (local file only) | `tests/test_config_capability.py` | `ci.yml` → `config-capability` | `already_proved` | settings / public | Lane installs `--extra config`, asserts import, sets `CHIRP_REQUIRE_DOTENV=1` + `CHIRP_CAPABILITY_LANE=config-capability` (#915/#917). Default `dev` still omits python-dotenv. |
| `redis` | `redis` | Redis sessions, secure_stack redis path, cache backend, signal backplane | **live Redis** for capability proof; failure-path without flaky network | `tests/test_redis_capability.py`; `tests/test_sessions.py` Redis class; `tests/test_secure_stack.py`; `tests/test_cache_redis_optional.py`; passkey Redis store | `ci.yml` → `redis-capability` | `already_proved` | middleware / realtime / cache | Lane installs `--extra redis`, starts Redis, asserts import, sets `CHIRP_REQUIRE_REDIS=1` + `CHIRP_TEST_REDIS_URL` (#906) and `CHIRP_CAPABILITY_LANE=redis-capability` (#917). Default `dev` still omits redis. |
| `all` | union of common deps (see pyproject; **excludes** `ui`, `config`, `redis`, `passkeys`, `ai-bedrock`, `benchmark`) | Install profile, not a capability | n/a | Profile resolution under #899 | n/a | `n_a` | settings / root | Aggregate extra. Composition integrity → epic #899 / decision #908. |
| `full` | same dep list as `all` today | Install profile, not a capability | n/a | Profile resolution under #899 | n/a | `n_a` | settings / root | Aggregate extra. Same gap ownership as `all`. |
| `benchmark` | peer frameworks (FastAPI, Flask, …) | Comparative / pelt benchmark tooling | Postgres for pelt-controlled | `benchmarks/*`, `tests/test_benchmarks_core.py` | `benchmarks.yml` (path-filtered) + pelt smoke on PG lane | `already_proved` | benchmarks | Tooling extra; not every-PR. Unexpected skip policy still #917 if a required bench step is asserted. |

## Gap → child issue map

| Gap | Priority | Child | Rationale |
| --- | --- | --- | --- |
| Live Redis capability + failure paths | P1 | #906 | **Closed by `redis-capability` lane** — `--extra redis` + Redis service + live session/cache/rate-limit proofs + unreachable-port failure path + `CHIRP_REQUIRE_REDIS=1`. |
| Argon2 authentication path | P1 | #909 | **Closed by `auth-capability` lane** — `--extra auth` + focused password tests + `CHIRP_REQUIRE_ARGON2=1`. |
| Remaining provider / heavy extras (`ai-bedrock`, `config`) | P2 | #915 | **Closed by `config-capability` + `ai-bedrock-capability` lanes** — credential-free / proportional proof; no third-party billing in PR CI. |
| Fail specialized lanes on unexpected skips | P1 | #917 | **Implemented** via `CHIRP_CAPABILITY_LANE` + `tests/capability/` registry (selector + skip assertions). |
| Publish evidence + local skip guidance | P2 | #926 | User-facing view of this matrix; install-doc drift for `passkeys` / `ai-bedrock`. |

No additional child issues are required to burn down #901 once this matrix is
approved.

## Explicit not-applicable receipts

| Topic | Receipt |
| --- | --- |
| Live OpenAI/Anthropic/etc. in PR CI | N/A — `ai` is proved via httpx + deterministic fixtures. Billable/network credentials stay out of PR CI (#898 boundary). |
| Live AWS Bedrock calls in PR CI | N/A — #915 may add botocore signing/fixture proof only. |
| `passkeys_e2e` browser job on every PR | N/A for PR matrix — unit/contract proof is the maintained lane; e2e remains documented opt-in (`-m passkeys_e2e`). Revisit if product policy requires browser WebAuthn in CI. |
| `all` / `full` as capability lanes | N/A — install aggregates; profile cleanliness is #899/#908. |
| Browser / query-interop lanes as extras | N/A — preserved infrastructure evidence, not PyPI extras. |

## Local contributor guidance (preview; full publish is #926)

| Situation | Expected locally | CI expectation |
| --- | --- | --- |
| No Redis | Redis session/secure_stack/live capability tests skip | `redis-capability` installs `chirp[redis]`, starts Redis, and must not skip (`CHIRP_REQUIRE_REDIS=1`, `CHIRP_TEST_REDIS_URL`, `CHIRP_CAPABILITY_LANE`) |
| No argon2-cffi | Argon2 password tests skip; scrypt path still runs | `auth-capability` installs `chirp[auth]` and must not skip (`CHIRP_REQUIRE_ARGON2=1` + `CHIRP_CAPABILITY_LANE`) |
| No botocore | Bedrock generate test soft-skips | `ai-bedrock-capability` installs `chirp[ai-bedrock]` and must not skip (`CHIRP_REQUIRE_BOTOCORE=1` + `CHIRP_CAPABILITY_LANE`) |
| No python-dotenv | `from_env` still works from process env | `config-capability` installs `chirp[config]` and must not skip (`CHIRP_REQUIRE_DOTENV=1` + `CHIRP_CAPABILITY_LANE`) |
| No Playwright | Browser tests importorskip | `browser-smoke` lane installs browser group + skip-fail |
| Minimal install without `dev` optional pkgs | forms/sessions/passkeys/markdown/ui may be absent | Do not treat minimal local skips as CI gaps |

## Skip-fail enforcement (#917)

Specialized CI lanes fail closed when required capability tests soft-skip or
fail to collect. Mechanism:

| Piece | Role |
| --- | --- |
| `tests/capability/lanes.py` | Declares lane name → capability, install hint, required nodeid selectors, allowed skip substrings |
| `tests/capability/plugin.py` | Pytest plugin (via root `conftest.py` `pytest_plugins`); inert unless `CHIRP_CAPABILITY_LANE` is set |
| `.github/workflows/ci.yml` | Each specialized pytest step sets `CHIRP_CAPABILITY_LANE=<name>` |

The default `test` job and ordinary local runs leave the env unset, so optional
dependency skips remain soft. New specialized lanes opt in by adding a
`CapabilityLane` registry entry and setting `CHIRP_CAPABILITY_LANE` on their CI
pytest step (as `redis-capability` does after #906).

## Acceptance #901

Acceptance #901: n/a (decision collateral only; no runtime behavior change).
Behavioral proof and skip-fail enforcement belong to #906, #909, #915, #917,
and publication to #926.
