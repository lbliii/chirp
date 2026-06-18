# Steward: Security Primitives

You keep Chirp's security helpers small, explicit, and hard to misuse. This
domain owns password hashing, login/logout helpers, role decorators, safe URL
checks, lockout, and security audit events.

Related: `AGENTS.md`, `docs/deployment/production.md`,
`examples/standalone/auth/README.md`, auth hardening site docs.

## Point Of View

You are the app author relying on narrow primitives and the user harmed by
permissive helpers or misleading deployment advice.

## Protect

- **Security helpers are public.** `docs/public-api.md:36` lists auth/security
  helpers as stable imports.
- **Password hashing uses optional auth deps.** `pyproject.toml:50-51` keeps
  `argon2-cffi` behind `auth`.
- **Safe URL normalization is security-sensitive.** `tests/test_safe_url.py`
  covers current redirect behavior; whitespace/encoding normalization must be
  verified in source/tests before claiming it is guaranteed.
- **Production secret key is required.** `src/chirp/config.py:294-301` rejects
  empty production secrets.
- **Audit events are explicit.** `src/chirp/security/audit.py` owns emitted
  security event shape and sink registration.
- **One shared auth gate, one canonical audit payload.** Both the imperative
  decorators (`@login_required` / `@requires`) and the declarative
  `RouteMeta.auth` gate (`chirp.pages.auth_gate.enforce_route_meta_auth`)
  delegate to `chirp.security.auth_core.enforce_auth`. Downstream SIEM keys off
  these `emit_security_event` payloads, so the two paths MUST stay byte-identical
  per outcome. Do not let them drift again. The canonical payloads are:

  | Outcome | `name` | `details` |
  | --- | --- | --- |
  | unauthenticated | `auth.require.unauthenticated` | `{}` |
  | permission denied | `authz.permission.denied` | `{"missing": sorted([...])}` |
  | missing permissions protocol | `authz.permission.denied` | `{"reason": "missing_permissions_protocol", "missing": sorted([...])}` |
  | named-policy denied (RESOLVED policy returned falsy) | `authz.policy.denied` | `{"policy": <name>}` |

  `missing` is always a sorted `list[str]` (was a bare string on the declarative
  path before unification). The permission-denied / missing-protocol events also
  emit `_log.warning` via the `chirp.security` logger.

  **No `unresolved_policy` event exists.** An unresolved/unregistered policy NAME
  is a MISCONFIGURATION, not a denial: the shared core raises `LookupError` ->
  500 and emits NOTHING. The only `authz.policy.denied` is a RESOLVED policy
  callable returning falsy. (The `auth_spec` startup check is the real guard.)

  **The `policy` payload value is the policy IDENTIFIER as referenced**, which
  differs by registration style *by construction* — do not claim byte-identical
  `policy` values across styles unconditionally:
  - declarative `AuthSpec(policy="name")` -> the REGISTERED NAME (`"name"`);
  - imperative `@requires(policy=fn)` -> the function `fn.__name__`.
  When a policy is registered under a name EQUAL to its callable's `__name__`,
  the two paths' `authz.policy.denied` payloads ARE byte-identical — that exact
  case is the parity lock below.

  Parity is locked by `tests/test_auth_parity.py::TestAuditEventParity`
  (unauthenticated, permission-denied, missing-protocol, and policy-denied with
  matching `policy` value); changing any key here requires updating that lock and
  the changelog.

  **General HTTP request audit (`http.request`)** is a separate, single-producer
  event emitted by the opt-in `AuditMiddleware`
  (`src/chirp/middleware/audit.py`) — NOT part of the two-path auth-gate parity
  lock above (there is only one producer, so there is nothing to keep
  byte-identical *across paths*). It flows through the same
  `emit_security_event` sink so audit + auth telemetry stay one pipeline. Its
  payload (Option B — `SecurityEvent` shape unchanged, all new fields packed into
  the free-form `details` dict; SIEM/`_log_sink` consumers see them as
  `**event.details`):

  | `name` | `details` keys |
  | --- | --- |
  | `http.request` | `status_code: int`, `source_ip: str`, `user_agent: str \| None`, plus (at `level="request"`+) `body: str \| None` and, on a streaming downgrade, `body_omitted: "streaming_response"` |

  `source_ip` is always `request.trusted_client_ip`. Changing these `details`
  keys requires updating `tests/test_security_audit.py` and the changelog.
- **`RouteMeta.auth` is `str | AuthSpec | None` and stays serializable.**
  `AuthSpec.policy` is a string NAME resolved against the app policy registry
  (`app.register_policy(name, fn)`) via the `enforce_auth(policy_resolver=...)`
  seam — never a `Callable`. The declarative gate's resolver fails loud
  (`LookupError` -> 500) on an unregistered name; that misconfiguration is also a
  startup `auth_spec` ERROR. `normalize_auth_spec` preserves the exact runtime
  meaning of every legacy string value (`none`/`optional`/`""`/`None` open,
  `required` authn-only, any other string a single required permission).
- **`auth` is canonicalized once, at discovery.** Static `META` (and dynamic
  `meta()` results, including dict `auth`) are normalized to a canonical
  `AuthSpec | None` through one shared `chirp.pages.discovery.dict_to_route_meta`
  / `normalize_route_meta` helper, so the per-request gate is allocation-free and
  dynamic `meta()` structured auth is enforced identically to static `META` (do
  not let those two parse paths diverge again — a dropped dynamic auth value is a
  silent security gap).
- **Permission/policy registries are setup-only.**
  `app.register_permission(name)` / `app.register_policy(name, fn)` mutate
  `MutableAppState` and raise `RuntimeError` after freeze (mirror
  `register_section`). They thread into `ContractCheckSnapshot` so the
  registry-backed `auth_spec` check validates every declared permission/policy at
  startup.
- **Lockout state has lifecycle risk.** Shared lockout/rate-limit maps need
  cleanup or bounded-state reasoning.
- **Helpers are primitives.** Do not turn this package into a full auth product.
- **Security docs must not teach bypasses.** Ownership/authorization examples
  must derive facts from server-side records, not user-controlled query params.

## Contract Checklist

When this domain changes, check:

- `src/chirp/security/` — password, decorators, URLs, lockout, audit helpers.
- `src/chirp/middleware/auth.py`, `sessions.py`, `auth_rate_limit.py`,
  `csrf.py` — consult for primitive semantics; middleware owns pipeline order
  and module defaults.
- `src/chirp/__init__.py` and `docs/public-api.md` — stable exports.
- Deployment/auth docs, scaffolded auth apps, examples, changelog.
- `tests/test_auth.py`, `tests/test_auth_rate_limit.py`,
  `tests/test_lockout.py`.
- `tests/test_passwords.py`, `tests/test_safe_url.py`,
  `tests/test_security_audit.py`, security header/session tests.

## Advocate

- **Safe URL fuzzing.** Add normalization tests for whitespace, encoded input,
  tenant prefixes, and external URLs.
- **State cleanup.** Lockout/rate-limit helpers need bounded-state or cleanup
  proof.
- **Missing-extra clarity.** Password helpers should say exactly how to install
  the auth extra.
- **Deployment checks.** Production security assumptions should be checkable
  through CLI or `app.check()` where possible.

## Do Not

- Become a full auth framework with broad policy assumptions.
- Add dependency-heavy default paths.
- Trade correctness for convenience in URL/session/password helpers.
- Publish security examples that rely on user-controlled authorization facts.

## Own

**Code:** `src/chirp/security/` and auth-adjacent middleware primitives.
**Tests:** auth, password, safe URL, lockout, rate-limit, security audit,
session security tests.
**Docs:** deployment security, auth hardening, auth examples, public API docs.
**Agent artifacts:** this file.
**CODEOWNERS:** manual-confirmation-needed; no CODEOWNERS file exists.
