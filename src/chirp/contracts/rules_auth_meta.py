"""Auth-wiring contract checks — AuthMiddleware presence + auth-spec typos.

Two env-aware, deploy-escalating rules that guard the auth surface a route
*declares* against the runtime wiring that surface needs. Both mirror
``rules_security_stack`` / ``rules_cookie_secure``: middleware is detected by
class **name** (never ``isinstance``, never importing middleware into the
contracts layer), severity is read from ``config.env`` so ``chirp check
--deploy`` escalates via the production-posture config view, and the
"mutating route" / class-name helpers are reused from ``rules_security_stack``
rather than re-derived.

Why this matters — a route can declare auth two ways, both of which 500/403 at
request time when the wiring is wrong, with NO startup signal otherwise:

- ``RouteMeta.auth`` (filesystem pages via ``_meta.py``): ``None`` / ``"none"`` /
  ``"optional"`` are open; ``"required"`` is authn-required; **any other
  non-empty string is treated as a single required PERMISSION**
  (see :func:`chirp.pages.auth_gate.enforce_route_meta_auth`).
- ``@login_required`` / ``@requires`` decorators on ``@app.route`` handlers,
  which now carry a static ``_chirp_requires_auth`` marker on the outermost
  wrapper so a check can prove the handler is auth-gated without executing it
  (the Marker phase; ``@wraps`` keeps the marker reachable on the stored
  handler while ``inspect.unwrap`` still reaches the inner handler).

Both paths call ``get_user()``
(:func:`chirp.middleware.auth.get_user`), which raises ``LookupError`` → a 500
at request time when ``AuthMiddleware`` is absent from the stack.

Categories:

- ``auth_middleware``: a route DECLARES auth (static ``RouteMeta.auth`` is
  non-open, or its handler carries the ``_chirp_requires_auth`` marker) but no
  ``AuthMiddleware`` is registered. Without it, ``get_user()`` raises
  ``LookupError`` → 500. Env-aware: ERROR in production, WARNING in staging,
  silent in development (the dev 500 surfaces it locally — a standing dev
  WARNING would just be noise, matching ``security_stack``). Dynamic ``meta()``
  pages (``meta_provider_paths``) are a static blind spot: never false-ERRORed,
  but a single INFO notes that auth wiring could not be statically verified for
  them.

- ``auth_spec``: the silent-403 permission-typo class. A ``RouteMeta.auth`` that
  is a case/whitespace variant of a reserved token (``"Required"``,
  ``"REQUIRED"``, ``" required "``, ``"None"``, ``"Optional"``) or
  empty-after-strip is almost certainly meant to be the reserved token but is
  instead treated as a required PERMISSION named that string — so it 403s
  forever. HIGH-SIGNAL ONLY: plausible permission names (``"admin"``) are NOT
  flagged — without a permission registry (a later wave) we cannot know them,
  and false positives erode trust. Env-aware like ``auth_middleware``.
"""

import inspect
from typing import TYPE_CHECKING, Any

from chirp.contracts.types import ContractIssue, Severity

if TYPE_CHECKING:
    from chirp.routing.router import Router

# Detected by class NAME (see module docstring) — no middleware import. The fix
# message names SessionMiddleware (AuthMiddleware sits after it in the stack) but
# only AuthMiddleware presence is checked here; SessionMiddleware presence is
# security_stack's concern.
_AUTH_MIDDLEWARE = "AuthMiddleware"

# Static introspection marker set by @login_required / @requires on the
# outermost returned wrapper (the Marker phase). Read off the stored handler.
_AUTH_MARKER = "_chirp_requires_auth"

# Reserved RouteMeta.auth tokens that mean "open" or "authn-required" — anything
# else is treated as a required PERMISSION. ``enforce_route_meta_auth`` treats
# ``None`` and these (case-sensitive, no surrounding whitespace) specially.
_OPEN_TOKENS = frozenset({"none", "optional"})
_RESERVED_TOKENS = frozenset({"none", "optional", "required"})

# Max edit distance from a reserved token at which a non-reserved value is read
# as a near-miss TYPO (e.g. 'requied' -> 'required', distance 1) rather than an
# intended permission name. Deliberately tight (<= 2): real permission names
# (admin/editor/moderator/billing.read) are all distance >= 4 from every reserved
# token, so this stays high-signal and never flags a plausible permission.
_TYPO_EDIT_DISTANCE = 2


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein distance between ``a`` and ``b`` (insert/delete/substitute).

    Small DP — auth values are tiny strings, so the O(len(a)*len(b)) table is
    trivially cheap and runs only on the handful of declared, non-reserved auth
    values an app actually ships.
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


def _near_reserved_token(value: str) -> bool:
    """True when ``value`` (already lowercased+stripped, non-reserved) is a tight
    near-miss of ``"required"`` — a likely typo (e.g. 'requied' -> 'required').

    Scoped to ``"required"`` ONLY, the one reserved token long and specific
    enough to attract typos. The short open tokens (``none``/``optional``) are
    deliberately NOT in the edit-distance neighbourhood: their distance-2 ball
    contains real words (``node``/``note`` near ``none``), which would be false
    positives — case/whitespace variants of those (``None``/``Optional``) are
    still caught by the variant branch. Bounded by :data:`_TYPO_EDIT_DISTANCE`
    so realistic permission names (``admin``/``editor``/``moderator`` are all
    distance >= 5 from ``required``) are never flagged.
    """
    return 0 < _edit_distance(value, "required") <= _TYPO_EDIT_DISTANCE


def _middleware_class_names(middleware_list: list[Any]) -> set[str]:
    return {type(mw).__name__ for mw in middleware_list}


def _auth_spec_is_open(auth: Any) -> bool:
    """True when a static ``RouteMeta.auth`` declares no gate.

    Mirrors :func:`chirp.security.auth_core.normalize_auth_spec`: ``None`` and
    the falsy/empty string case are open, as are the exact reserved open tokens
    ``"none"`` / ``"optional"``. A bare ``"required"``, any other non-empty
    string, OR a structured ``AuthSpec`` DECLARES auth (an ``AuthSpec`` always
    gates).
    """
    if auth is None:
        return True
    if not isinstance(auth, str):
        # A structured AuthSpec always declares auth.
        return False
    if not auth:
        return True
    return auth in _OPEN_TOKENS


def _handler_declares_auth(route: Any) -> bool:
    """True when a route's handler carries the static auth-gate marker.

    The marker (:data:`_AUTH_MARKER`) is set by ``@login_required`` / ``@requires``
    on the OUTERMOST wrapper the router stores — NOT the inner handler — so it
    must be read off ``route.handler`` (and, for mounted pages,
    ``route.page_source_handler``) directly, before ``inspect.unwrap`` would
    drop to the inner handler and lose it. We additionally walk the unwrap chain
    so a marker that landed on an inner layer (e.g. a stacked decorator
    arrangement) is still detected. This mirrors how ``rules_nojs_floor`` resolves
    the user's real handler via ``page_source_handler`` then ``inspect.unwrap``.
    """
    candidates: list[Any] = []
    page_src = getattr(route, "page_source_handler", None)
    if page_src is not None:
        candidates.append(page_src)
    handler = getattr(route, "handler", None)
    if handler is not None:
        candidates.append(handler)

    for obj in candidates:
        if getattr(obj, _AUTH_MARKER, False):
            return True
        try:
            inner = inspect.unwrap(obj)
        except ValueError:  # pragma: no cover - cyclic __wrapped__ chain
            continue
        if inner is not obj and getattr(inner, _AUTH_MARKER, False):
            return True
    return False


def check_auth_middleware(
    router: Router,
    config: Any,
    middleware_list: list[Any],
    route_metas: dict[str, Any] | None = None,
    meta_provider_paths: set[str] | None = None,
) -> list[ContractIssue]:
    """Flag auth-declaring routes when ``AuthMiddleware`` is absent.

    A route "declares auth" when EITHER:

    - its static ``RouteMeta.auth`` (from *route_metas*, keyed by URL path) is
      non-open — not ``None`` / ``"none"`` / ``"optional"``; or
    - its handler carries the ``_chirp_requires_auth`` marker set by
      ``@login_required`` / ``@requires`` (see :func:`_handler_declares_auth`).

    If ANY auth-declaring route exists and no ``AuthMiddleware`` is registered,
    emit ``auth_middleware`` naming a concrete offending route + the fix.
    Without ``AuthMiddleware``, ``get_user()`` raises ``LookupError`` → 500 at
    request time. Severity is env-aware: ERROR in production, WARNING in staging,
    silent in development (the dev 500 surfaces it locally — matching
    ``security_stack``; no standing dev WARNING).

    Dynamic ``meta()`` pages (*meta_provider_paths*) are a static blind spot: a
    page whose ``_meta.py`` defines ``meta()`` registers a meta provider with
    static ``meta`` left ``None``, so its auth value is invisible here. Those
    paths are excluded from the ERROR/WARNING (no false positive) and, when
    ``AuthMiddleware`` is absent and such pages exist, get a single INFO noting
    auth wiring could not be statically verified for them — mirroring how
    ``check_section_coverage`` handles ``meta_provider_paths``.
    """
    issues: list[ContractIssue] = []

    route_metas = route_metas or {}
    skip_meta_provider = meta_provider_paths or set()

    if _AUTH_MIDDLEWARE in _middleware_class_names(middleware_list):
        # AuthMiddleware present — get_user() resolves, nothing to flag (the
        # auth_spec rule and request-time enforcement own the rest).
        return issues

    # Find the first concrete offending route path for an actionable message.
    offending_path: str | None = None

    # (a) static RouteMeta.auth — skip dynamic meta() pages (blind spot).
    for path, meta in route_metas.items():
        if path in skip_meta_provider:
            continue
        auth = getattr(meta, "auth", None)
        if not _auth_spec_is_open(auth):
            offending_path = path
            break

    # (b) decorator marker on @app.route handlers (and mounted page handlers).
    if offending_path is None:
        for route in getattr(router, "routes", []):
            if _handler_declares_auth(route):
                offending_path = getattr(route, "path", None) or "<route>"
                break

    if offending_path is not None:
        env = getattr(config, "env", "development")
        if env in ("production", "staging"):
            severity = Severity.ERROR if env == "production" else Severity.WARNING
            issues.append(
                ContractIssue(
                    severity=severity,
                    category="auth_middleware",
                    message=(
                        f"Route '{offending_path}' declares auth "
                        "(RouteMeta.auth or @login_required/@requires) but "
                        f"AuthMiddleware is not registered while env='{env}'. "
                        "The auth gate calls get_user(), which raises LookupError "
                        "-> a 500 at request time without AuthMiddleware. Register "
                        "AuthMiddleware after SessionMiddleware in the stack."
                    ),
                    route=offending_path,
                )
            )

    # Dynamic-meta blind spot: one INFO when AuthMiddleware is absent and dynamic
    # meta() pages exist (their auth value cannot be statically verified). Never
    # an ERROR — that would be a false positive for a page that is in fact open.
    if skip_meta_provider:
        provider = sorted(skip_meta_provider)[0]
        issues.append(
            ContractIssue(
                severity=Severity.INFO,
                category="auth_middleware",
                message=(
                    f"Page '{provider}' (and other dynamic meta() pages) defines "
                    "meta() at runtime, so its auth requirement cannot be checked "
                    "statically. If any dynamic-meta page is auth-gated, ensure "
                    "AuthMiddleware is registered after SessionMiddleware — "
                    "otherwise the auth gate raises LookupError -> 500 at request "
                    "time."
                ),
                route=provider,
            )
        )

    return issues


def _permission_names(auth: Any) -> tuple[str, ...]:
    """Return the declared permission name(s) for an ``auth`` value.

    - a bare non-open ``str`` -> that single permission (the legacy shape);
    - an ``AuthSpec`` -> its ``permissions`` tuple (canonical, post-discovery);
    - anything open / authn-only -> ``()``.

    Mirrors :func:`chirp.security.auth_core.normalize_auth_spec`: ``required`` and
    the open tokens declare no permission, so they are never inspected here.
    """
    if isinstance(auth, str):
        if not auth or auth in _RESERVED_TOKENS:
            return ()
        return (auth,)
    permissions = getattr(auth, "permissions", None)
    if isinstance(permissions, (tuple, list)):
        return tuple(str(p) for p in permissions)
    return ()


def _scope_names(auth: Any) -> tuple[str, ...]:
    """Return the declared machine-token scope name(s) for an ``auth`` value.

    Only a structured ``AuthSpec`` carries ``scopes`` — a bare string ``auth``
    never produces scopes (it normalizes to a permission). The machine-auth
    counterpart to :func:`_permission_names`.
    """
    scopes = getattr(auth, "scopes", None)
    if isinstance(scopes, (tuple, list)):
        return tuple(str(s) for s in scopes)
    return ()


def _looks_like_reserved_token_confusion(name: str) -> bool:
    """True when a permission *name* is almost certainly a botched reserved token.

    The high-signal heuristic used when NO permission registry is declared:

    - empty-after-strip / whitespace-only (a permission named ``""``);
    - a case/whitespace variant of a reserved token (``"Required"`` / ``" required "``
      / ``"None"`` / ``"Optional"``);
    - a tight misspelling of ``"required"`` (edit distance <= 2, e.g. ``"requied"``).

    Plausible permission names (``"admin"``, ``"billing.read"``) are NOT flagged.
    """
    stripped = name.strip()
    lowered = stripped.lower()
    return (
        not stripped
        or (lowered in _RESERVED_TOKENS and name not in _RESERVED_TOKENS)
        or _near_reserved_token(lowered)
    )


def check_auth_spec(
    config: Any,
    route_metas: dict[str, Any] | None = None,
    meta_provider_paths: set[str] | None = None,
    permission_registry: frozenset[str] | set[str] | None = None,
    policy_registry: frozenset[str] | set[str] | None = None,
    scope_registry: frozenset[str] | set[str] | None = None,
) -> list[ContractIssue]:
    """Flag declared ``RouteMeta.auth`` permissions/policies/scopes that fail silently.

    A non-reserved ``auth`` string (or an ``AuthSpec.permissions`` entry) is a
    required PERMISSION; an ``AuthSpec.policy`` is a NAME resolved against the app
    policy registry; an ``AuthSpec.scopes`` entry is a machine-token SCOPE. All
    403 (permission/scope) / 500 (unresolved policy) at request time when wrong,
    with no other startup signal.

    PERMISSIONS, POLICIES, and SCOPES are validated by design:

    - **Permissions are opt-in.** They are only validated against
      *permission_registry* when that registry is non-empty (a declared
      ``app.register_permission``); with no permission registry the high-signal
      reserved-token-confusion heuristic runs instead (``"Required"`` /
      ``" required "`` / ``"requied"`` / whitespace-only). Plausible permission
      names (``"admin"``) are never flagged without a registry — false positives
      erode trust.
    - **Policies always resolve.** A referenced ``AuthSpec.policy`` NAME not in
      *policy_registry* is ALWAYS an ERROR (env-aware), INCLUDING when
      *policy_registry* is empty. An ``AuthSpec(policy="x")`` with no
      ``register_policy("x")`` is unconditionally a bug — it raises
      ``LookupError`` -> 500 at request time, so there is no false-positive risk.
    - **Scopes are opt-in** (machine-auth axis). They are validated against
      *scope_registry* only when that registry is non-empty (a declared
      ``app.register_scope``); an ``AuthSpec.scopes`` entry not in the declared
      set is an env-aware ERROR. With no scope registry scopes are free strings
      — there is no typo heuristic (a scope is an arbitrary machine token, so a
      plausible-name heuristic has no signal). This folds into the EXISTING
      ``auth_spec`` category — no new category, no severity change.

    Env-aware via *config.env* (ERROR production / WARNING staging / silent
    development), same as ``auth_middleware``. Dynamic ``meta()`` pages
    (*meta_provider_paths*) are skipped — their auth value is not in
    *route_metas*.
    """
    issues: list[ContractIssue] = []

    route_metas = route_metas or {}
    skip_meta_provider = meta_provider_paths or set()
    perms = permission_registry or frozenset()
    policies = policy_registry or frozenset()
    scopes_registry = scope_registry or frozenset()

    env = getattr(config, "env", "development")
    if env not in ("production", "staging"):
        return issues
    severity = Severity.ERROR if env == "production" else Severity.WARNING

    for path, meta in route_metas.items():
        if path in skip_meta_provider:
            continue
        auth = getattr(meta, "auth", None)
        # None / "" / open token / authn-only "required" declare no permission.
        if auth is None:
            continue

        declared_perms = _permission_names(auth)

        # Precise mode validates every declared permission against the registry,
        # but ONLY when a PERMISSION registry exists. A policy-only registry (or
        # no registry) leaves permission validation to the high-signal heuristic
        # so plausible names like "admin" are not falsely ERRORed.
        if perms:
            issues.extend(
                ContractIssue(
                    severity=severity,
                    category="auth_spec",
                    message=(
                        f"auth permission {perm!r} on {path} is not a registered "
                        "permission. Declare it with app.register_permission(name) "
                        "or fix the typo; an unknown permission silently 403s."
                    ),
                    route=path,
                )
                for perm in declared_perms
                if perm not in perms
            )
        else:
            issues.extend(
                _typo_issue(severity, perm, path)
                for perm in declared_perms
                if _looks_like_reserved_token_confusion(perm)
            )

        # Named-policy validation. UNLIKE permissions (opt-in: only validated
        # when a permission registry exists), a referenced policy NAME must
        # ALWAYS resolve — including when the policy registry is EMPTY. An
        # AuthSpec(policy="x") with no register_policy("x") is always a bug: it
        # raises LookupError -> 500 at request time. This asymmetry is
        # intentional.
        policy = getattr(auth, "policy", None)
        if policy is not None and policy not in policies:
            issues.append(
                ContractIssue(
                    severity=severity,
                    category="auth_spec",
                    message=(
                        f"auth policy {policy!r} on {path} is not a registered "
                        "policy. Register it with app.register_policy(name, fn); an "
                        "unresolved policy name fails loud (500) at request time."
                    ),
                    route=path,
                )
            )

        # Scope validation (machine-auth axis). Opt-in like permissions: only
        # validated when a SCOPE registry exists. With no registry, scopes are
        # free strings (no typo heuristic — a scope is an arbitrary token). This
        # folds into the existing auth_spec category (no new category).
        if scopes_registry:
            issues.extend(
                ContractIssue(
                    severity=severity,
                    category="auth_spec",
                    message=(
                        f"auth scope {scope!r} on {path} is not a registered "
                        "scope. Declare it with app.register_scope(name) or fix "
                        "the typo; an unknown scope silently 403s machine clients."
                    ),
                    route=path,
                )
                for scope in _scope_names(auth)
                if scope not in scopes_registry
            )

    return issues


def _typo_issue(severity: Severity, name: str, path: str) -> ContractIssue:
    """Build the reserved-token-confusion ``auth_spec`` issue for a permission."""
    return ContractIssue(
        severity=severity,
        category="auth_spec",
        message=(
            f"auth={name!r} on {path} looks like a typo of a reserved "
            "token (none/optional/required); a bare string is treated "
            "as a required PERMISSION and will silently 403."
        ),
        route=path,
    )
