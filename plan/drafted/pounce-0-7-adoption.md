# Plan: Pounce 0.7 Adoption

**Status**: Drafted for implementation
**Created**: 2026-05-10
**Source**: Pounce 0.7.0 release, steward consultation, local Chirp/Pounce audit
**Dependency floor**: `bengal-pounce>=0.7.0`

## Goal

Adopt Pounce 0.7 where it improves Chirp's production operator story without
blurring ownership boundaries. Chirp owns hypermedia contracts, app lifecycle,
typed request/response handling, docs, examples, and CLI behavior. Pounce owns
server protocol parsing, socket workers, config inspection, and server-level
operator diagnostics.

## Non-Goals

- Do not wrap every Pounce CLI command in `chirp`.
- Do not make `chirp check` run `pounce check`; those checks have different
  failure domains.
- Do not make `chirp run` read `pounce.toml` without a separate config-loading
  design.
- Do not expose `/_pounce/info` casually or enable it by default.
- Do not add a Chirp WebSocket return type as part of Pounce adoption.
- Do not retest Pounce HTTP/2 or HTTP/3 parser internals in Chirp unless a
  Chirp deployment fixture depends on that behavior.

## Steward Consultation

Consulted:

- App lifecycle steward.
- CLI steward.
- Docs/site steward.
- Security/middleware steward.
- Server/runtime steward locally.

Timed out and closed:

- Test matrix steward.
- Benchmark steward.

Their domains are still represented in the proof plan below using their scoped
`AGENTS.md` checklists and local code audit.

## Convergence

The stewards converged on five points:

1. Pounce 0.7 is already adopted at the dependency level, but not fully adopted
   as an operator surface.
2. `chirp run --production` must not drift from `app.run()` production behavior.
3. Pounce config inspection should be documented as Pounce-native until Chirp
   deliberately supports Pounce config files.
4. Worker lifecycle semantics are the main correctness risk, especially
   `worker_mode="auto"` resolving to sync workers on Python 3.14t.
5. Security-facing settings such as trusted proxy authority, compression, and
   introspection need explicit public API decisions before implementation.

## Minority Reports And Tension

- Docs/site wants immediate operator guidance for `/_pounce/info`; security
  agrees only if the wording says it is disabled by default, loopback/admin-only,
  and not protected by Chirp middleware.
- CLI recommends documenting `pounce check` separately, not merging it into
  `chirp check`, because Pounce checks can fail on environment concerns such as
  port availability.
- App lifecycle sees worker hooks as a P1 correctness issue; security/docs see
  introspection and trusted proxy guidance as P1 operator issues. The sequence
  below handles the CLI/lifecycle correctness first, then docs/security config.

## Raw Steward Signals

### App Lifecycle

- P1: Per-worker lifecycle hooks must run in the worker mode Chirp selects by
  default. `worker_mode="auto"` can resolve to sync on Python 3.14t, while local
  Pounce 0.7 sync workers did not appear to emit `pounce.worker.startup` and
  `pounce.worker.shutdown` scopes.
- P1: Worker startup failures need defined semantics. Pounce paths may log and
  continue; Chirp needs either fail-loud required hooks or docs that worker
  hooks are best-effort.
- P2: Chirp forwards only a subset of Pounce lifecycle-critical config. Consider
  `startup_timeout`, `shutdown_timeout`, `header_timeout`, and
  `executor_threads_per_worker`.
- P2: `lifecycle_collector` is forwarded in dev but not production.
- P2: `worker_mode="subinterpreter"` is exposed by config but production launch
  does not pass an import path required by Pounce subinterpreter workers.

### CLI

- P1: `chirp run --production` omits `worker_mode` and `metrics_path`, while
  `app.run()` forwards them.
- P2: `pounce check` should be a separate deploy preflight, not folded into
  `chirp check`.
- P2: `pounce config schema` and `pounce config show` should be documented as
  Pounce-native inspection. `pounce.toml` is authoritative for `pounce serve`,
  not for Chirp surfaces today.
- P2: `/_pounce/info` is not currently exposed through Chirp config; keep it
  not-now unless a secure pass-through design lands.

### Docs And Site

- P1: Current production docs describe unprefixed env vars such as `WORKERS`,
  `METRICS_ENABLED`, and `QUEUE_ENABLED` that `AppConfig.from_env()` does not
  read. Split Chirp-native config from direct Pounce config.
- P1: Published site deployment docs omit or under-link operator details that
  exist in source docs, including Railway guidance.
- P1: Add safety guidance for `/_pounce/info`: disabled by default, loopback by
  default, redaction is not access control.
- P2: Dependency floor changes and operator-visible guidance need release
  collateral.

### Security And Middleware

- P1: Pounce 0.7 has trusted proxy handling, but Chirp does not expose or
  forward it. Chirp's auth rate limiter defaults to `x-forwarded-for`; that
  should not be trusted unless Pounce has normalized the client authority.
- P1: If introspection is exposed, document that it sits before the Chirp app
  and is not protected by Chirp middleware.
- P2: Pounce 0.7 enables HTTP response compression by default, while Chirp does
  not expose compression controls. Docs also imply SSE payload compression under
  a WebSocket heading, but Pounce disables compression for `text/event-stream`.
- P2: Do not map `app.add_middleware()` to Pounce server middleware hooks.
- P3: WebSocket compression is a Pounce pass-through only; Chirp's realtime
  contract remains SSE.

### Server Runtime

- P1: Keep Pounce protocol internals in Pounce. Chirp should prove its server
  wrappers, sync path, worker lifecycle scopes, terminal errors, and deployment
  docs align with Pounce 0.7.
- P2: Avoid adding REST/JSON side channels or runtime diagnostics that bypass
  Chirp's return-type architecture.

## Ranked Backlog

### 1. CLI And Production Launch Parity

**Status**: Done in `fix: align pounce production launch config`.

**Why**: `chirp run --production` must not ignore production settings that
`app.run()` honors.

**Scope**:

- Forward `worker_mode` and `metrics_path` from `chirp run --production`.
- Add a regression test that compares critical production kwargs forwarded by
  CLI and `ServerLauncher`.
- Forward `lifecycle_collector` into production server launch, matching dev.
- Add a clear preflight or runtime error for `worker_mode="subinterpreter"`
  unless the launch path can provide a Pounce app import path.

**Required proof**:

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p pytest_asyncio.plugin -p pytest_timeout tests/test_cli.py tests/test_cli_run.py tests/test_app/test_worker_lifecycle.py -q`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p pytest_asyncio.plugin -p pytest_timeout tests/test_startup_errors.py tests/test_sync_handler.py tests/test_sync_request.py -q`
- `.venv/bin/ty check src/chirp/`

**Completed proof**:

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p pytest_asyncio.plugin -p pytest_timeout tests/test_cli.py tests/test_cli_run.py tests/test_app/test_worker_lifecycle.py -q`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p pytest_asyncio.plugin -p pytest_timeout tests/test_startup_errors.py tests/test_sync_handler.py tests/test_sync_request.py -q`
- `.venv/bin/ty check src/chirp/`

**Collateral**:

- Deployment docs only if new public flags or behavior are added.

### 2. Worker Lifecycle Semantics

**Status**: Done in `fix: gate worker hooks to async pounce workers`.

**Why**: Worker hooks are a production contract. If Pounce sync workers do not
emit worker scopes, Chirp must either gate the combination or document it as
best-effort.

**Scope**:

- Create a real Pounce integration proof for `worker_mode="auto"` on Python
  3.14t, not only direct ASGI scope simulation.
- Decide required semantics for `@app.on_worker_startup` failures:
  fail-loud before serving or best-effort with loud documentation.
- If Pounce needs an upstream fix, record the upstream issue and gate Chirp's
  docs until it lands.

**Required proof**:

- Existing worker lifecycle tests plus a Pounce-backed smoke test if feasible.
- Startup-failure test showing whether a failed hook prevents serving or is
  reported as best-effort.

**Completed decision**:

- Chirp fails production startup when worker hooks are registered and Pounce
  resolves the effective worker mode to sync.
- Worker hook users must set `worker_mode="async"` explicitly.
- Pounce 0.7 async worker startup hook failures are documented as best-effort:
  Pounce logs and continues serving. Fail-loud worker startup needs an upstream
  Pounce change, tracked in
  [pounce#65](https://github.com/lbliii/pounce/issues/65).

**Completed proof**:

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p pytest_asyncio.plugin -p pytest_timeout tests/test_app/test_worker_lifecycle.py -q`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p pytest_asyncio.plugin -p pytest_timeout tests/test_startup_errors.py tests/test_sync_handler.py tests/test_sync_request.py -q`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p pytest_asyncio.plugin -p pytest_timeout tests/docs -q`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p pytest_asyncio.plugin -p pytest_timeout tests/test_freeze_site.py tests/test_search_index_v2.py tests/docs/test_site_link_drift.py -q`
- `.venv/bin/ty check src/chirp/`

**Collateral**:

- `site/content/docs/about/core-concepts/app-lifecycle.md`
- Thread-safety and production deployment docs.

### 3. Operator Docs And Config Boundary

**Why**: Pounce 0.7 adds useful operator commands, but Chirp must explain which
config path actually runs.

**Scope**:

- Add a deployment section that pairs:
  - `chirp check myapp:app --warnings-as-errors` for Chirp hypermedia
    contracts.
  - `pounce check --app myapp:app` for server import/config/TLS/port preflight.
- Document:
  - `pounce config schema --output-format toml-template`
  - `pounce config schema --output-format json`
  - `pounce config show --config pounce.toml --output-format toml`
  - `pounce serve --app myapp:app --config pounce.toml`
- State plainly that `pounce.toml` is Pounce-native today. `app.run()` and
  `chirp run` use `AppConfig` unless a later design changes that.
- Fix stale production docs that imply unsupported env vars are read by Chirp.
- Fix WebSocket/SSE compression wording: SSE is Chirp's realtime contract and
  Pounce intentionally avoids compressing `text/event-stream`.

**Required proof**:

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p pytest_asyncio.plugin -p pytest_timeout tests/docs -q`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p pytest_asyncio.plugin -p pytest_timeout tests/docs/test_site_link_drift.py tests/test_freeze_site.py -q`
- Add docs guards for unsupported env var claims if possible.

**Collateral**:

- README deployment paragraph if it mentions Pounce production commands.
- Release/towncrier fragment for the dependency floor and operator guidance.

### 4. Security-Facing Pounce Config Decisions

**Why**: Trusted proxy authority, compression, and introspection affect security
and operator behavior. They need an explicit API decision before code changes.

**Stop and ask before implementing public config fields.**

**Candidate config**:

- `trusted_proxy_hosts` -> Pounce `trusted_hosts`
- `compression` -> Pounce `compression`
- `compression_min_size` -> Pounce `compression_min_size`
- Optional, later: `pounce_introspection_enabled`,
  `pounce_introspection_bind`, `pounce_introspection_path`

**Scope if accepted**:

- Forward accepted fields through `AppConfig`, `ServerLauncher`,
  `run_production_server`, and CLI where appropriate.
- Change `AuthRateLimitMiddleware` guidance and examples to prefer
  `request.client` after trusted proxy normalization.
- Add security-check warnings for wildcard trusted proxies or public
  introspection if the fields become public.

**Required proof**:

- Config forwarding tests.
- Auth rate-limit test proving spoofed `X-Forwarded-For` is not trusted by
  default.
- Security docs and custom middleware example update.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p pytest_asyncio.plugin -p pytest_timeout tests/test_auth_rate_limit.py tests/test_security_headers.py tests/test_allowed_hosts.py -q`

**Collateral**:

- `docs/public-api.md` and config docs for any new `AppConfig` fields.
- Changelog fragment for public API/security behavior.

### 5. Pounce 0.7 Introspection Guidance

**Why**: `/_pounce/info` is useful operationally, but easy to expose
incorrectly.

**Scope**:

- Document it only as disabled-by-default and Pounce-native until Chirp exposes
  explicit config fields.
- State that it is handled before Chirp middleware; do not rely on Chirp auth,
  CSRF, or allowed-host middleware to protect it.
- Recommend loopback, private admin network, VPN, SSH tunnel, or port-forward
  access only.

**Required proof**:

- If only docs: docs/link tests.
- If code/config is added: production server E2E proving disabled-by-default,
  redacted response shape, and public-bind warning.

### 6. Benchmark Fixture Adoption

**Why**: Pounce 0.7 includes Bengal and Chirp workload fixtures. Chirp should
use them to calibrate claims, not copy numbers into marketing.

**Scope**:

- Locate Pounce benchmark fixtures and map them to Chirp's current
  `benchmarks/` workloads.
- Run the smallest smoke benchmark locally.
- Update benchmark docs only if the new fixtures change a claim or methodology.
- Keep artifact schema changes intentional.

**Required proof**:

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p pytest_asyncio.plugin -p pytest_timeout tests/test_benchmarks_core.py -q`
- `python -m benchmarks.core` or the repo's benchmark smoke command.
- Benchmark artifact with command, environment, Pounce/Chirp/Kida versions, and
  caveats if publishing numbers.

**Collateral**:

- `benchmarks/README.md`
- `docs/benchmark-plan.md`
- `docs/benchmark-deep-dive.md`

### 7. Release Collateral

**Why**: Pounce 0.7 is now Chirp's dependency floor and has user-visible
operator implications.

**Scope**:

- Add a towncrier fragment.
- Mention:
  - `bengal-pounce>=0.7.0`
  - separate `chirp check` and `pounce check` preflights
  - Pounce config inspection commands
  - any newly exposed config fields or intentionally deferred fields

**Required proof**:

- `make changelog-draft` or equivalent project changelog draft command.

## Parity Matrix

| Contract | API/CLI | Programmatic | Protocol | Schema/Types | Docs | Examples | Tests |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Production launch config | `chirp run --production` forwards same critical settings | `app.run()` / `run_production_server()` stay aligned | Pounce `ServerConfig` receives intended values | Any new `AppConfig` fields documented | Production docs | N/A unless CLI examples change | CLI + server launch tests |
| Worker lifecycle | Avoid unsupported worker modes or prove scopes fire | `on_worker_startup` semantics clear | Pounce worker scopes/failures understood | No new types unless config grows | App lifecycle docs | N/A | Direct + Pounce-backed lifecycle tests |
| Config inspection | Document Pounce-native commands | Do not imply `pounce.toml` affects `app.run()` | Pounce owns config merge/show/check | No Chirp schema until accepted | Deployment docs | N/A | Docs guards |
| Trusted proxy authority | Optional future CLI/config pass-through | `AppConfig` if accepted | Pounce normalizes trusted headers before Chirp | New config fields if accepted | Security/deployment docs | Custom middleware example | Forwarding + auth rate-limit tests |
| Introspection | Do not expose by default | Optional future `AppConfig` if accepted | Pounce handles before Chirp app | New config fields if accepted | Admin-only guidance | N/A | Disabled/redaction/public-bind tests if exposed |
| Benchmarks | N/A | N/A | Pounce workload fixtures compared carefully | Artifact schema stable | Benchmark docs | Benchmark fixtures | Benchmark smoke |

## Risks

- Teaching `pounce.toml` without saying Chirp ignores it today would create a
  serious operator footgun.
- Worker hooks can look reliable in unit tests while being skipped or
  best-effort in production worker modes.
- Trusted proxy and rate-limit behavior can be security-sensitive; do not rely
  on raw forwarded headers by default.
- `/_pounce/info` can bypass Chirp middleware because it is server-level.
- Benchmark claims can drift into marketing if not tied to commands and
  environment metadata.

## Not Now

- Broad Pounce CLI wrapping.
- Pounce server middleware as a Chirp public API.
- Public introspection by default.
- Chirp WebSocket return types.
- Pounce HTTP/2/HTTP/3 parser regression tests in Chirp.
- Automatic `pounce.toml` loading by `chirp run` without a design review.
