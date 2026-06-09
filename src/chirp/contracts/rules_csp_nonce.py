"""CSP-nonce contract check — framework inline scripts need a nonce mechanism (#181, #195).

When an app ships a **nonce-based / inline-forbidding** Content-Security-Policy
(a ``script-src`` that does *not* include ``'unsafe-inline'``), every inline
``<script>`` the framework emits must carry a live ``nonce`` attribute or it is
silently blocked by the browser.

As of #195 the framework injects every compile-time inline ``<script>`` through a
per-request snippet **factory** (``nonce -> snippet``), so each script carries the
live nonce **whenever a per-request nonce mechanism is active** — that is,
``CSPNonceMiddleware`` is wired, or ``config.csp_nonce_enabled`` is set (which
auto-wires it at freeze time). The framework's inline-script surfaces are:

- the Alpine ``safeData`` bootstrap (``alpine=True``, non-CSP build),
- the htmx ``safe_target`` script,
- the ``sse_lifecycle`` script,
- the event ``delegation`` script,
- the ``view_transitions`` script (``"htmx"``/``"full"`` modes),
- the islands runtime bootstrap (``islands=True``),
- the ``speculation_rules`` ``<script type="speculationrules">``,
- Suspense initial-load OOB scripts (nonced via the request lifecycle, #181).

The **genuinely un-nonceable** case this rule flags is therefore narrow: an
inline-forbidding CSP is in force **but there is no per-request nonce mechanism**
— e.g. a static ``SecurityHeadersMiddleware`` CSP whose ``script-src`` drops
``'unsafe-inline'`` *without* ``CSPNonceMiddleware`` and without
``csp_nonce_enabled``. In that configuration ``csp_nonce()`` returns ``""`` so the
factories emit un-nonced scripts that the browser blocks — and at least one
framework inline-script feature is enabled, so something actually breaks.

Severity is env-aware, mirroring ``rules_security_stack``: ERROR in production,
WARNING in staging, **silent** in development (the default) so dev apps and
shipped examples stay clean.

The rule stays **silent** when:

- no inline-forbidding policy is in force (no nonce-only CSP), **or**
- a per-request nonce mechanism is active (everything is nonceable), **or**
- no framework inline-script feature is enabled (nothing to block).

The ``@alpinejs/csp`` build (``alpine_csp=True``) ships no inline bootstrap, so it
is never counted as an inline-script feature.

Detection follows ``rules_security_stack``: middleware is matched by class
**name** (``type(mw).__name__``) so this layer never imports middleware classes.
The CSP string is read from ``SecurityHeadersMiddleware`` config or
``config.content_security_policy`` and parsed for an inline-forbidding
``script-src``. This check does not double-fire with ``security_stack``
(CSRF/Session presence) or ``csrf_session`` (stack ordering).
"""

from typing import TYPE_CHECKING, Any

from chirp.contracts.types import ContractIssue, Severity

if TYPE_CHECKING:
    from chirp.routing.router import Router

_SECURITY_HEADERS_MIDDLEWARE = "SecurityHeadersMiddleware"
_CSP_NONCE_MIDDLEWARE = "CSPNonceMiddleware"


def _script_src_directive(csp: str) -> str | None:
    """Return the ``script-src`` directive value from a CSP string, or None.

    Falls back to ``default-src`` per the CSP spec when ``script-src`` is absent.
    """
    src: str | None = None
    default: str | None = None
    for directive in csp.split(";"):
        directive = directive.strip()
        if not directive:
            continue
        name, _, value = directive.partition(" ")
        name = name.lower()
        if name == "script-src":
            src = value.strip()
        elif name == "default-src":
            default = value.strip()
    return src if src is not None else default


def _forbids_inline(csp: str) -> bool:
    """True when the effective script-src forbids inline scripts.

    A CSP forbids inline scripts when a ``script-src`` (or fallback
    ``default-src``) is present and does *not* list ``'unsafe-inline'``.
    """
    directive = _script_src_directive(csp)
    if directive is None:
        return False
    return "'unsafe-inline'" not in directive


def _effective_csp(config: Any, middleware_list: list[Any]) -> str | None:
    """Resolve the static CSP string the app will actually send.

    Order of precedence mirrors how responses are built: an explicit
    ``SecurityHeadersMiddleware`` config wins; otherwise the app-level
    ``content_security_policy`` (if any). This is the *static* CSP only — the
    dynamic per-request nonce CSP from ``CSPNonceMiddleware`` is detected
    separately (it is always nonce-bearing by construction, so its presence is a
    nonce mechanism, not an un-nonceable hazard).
    """
    for mw in middleware_list:
        if type(mw).__name__ != _SECURITY_HEADERS_MIDDLEWARE:
            continue
        cfg = getattr(mw, "config", None)
        csp = getattr(cfg, "content_security_policy", None)
        if csp:
            return csp
    return getattr(config, "content_security_policy", None)


def _enabled_inline_script_features(config: Any) -> list[str]:
    """Return the framework inline-script features enabled on ``config``.

    Each entry names a compile-time inline ``<script>`` the framework injects.
    ``alpine_csp=True`` is excluded because the ``@alpinejs/csp`` build ships no
    inline bootstrap. ``view_transitions`` is counted only in its non-``off``
    modes (``True``/``"htmx"``/``"full"``); its ``"full"`` HEAD markup is a
    ``<style>`` governed by ``style-src``, but the script snippet is always
    present in non-``off`` modes.
    """
    features: list[str] = []

    if getattr(config, "alpine", False) and not getattr(config, "alpine_csp", False):
        features.append("alpine")
    if getattr(config, "safe_target", False):
        features.append("safe_target")
    if getattr(config, "sse_lifecycle", False):
        features.append("sse_lifecycle")
    if getattr(config, "delegation", False):
        features.append("delegation")
    if getattr(config, "islands", False):
        features.append("islands")

    vt = getattr(config, "view_transitions", False)
    if vt not in (False, "off"):
        features.append("view_transitions")

    sr = getattr(config, "speculation_rules", False)
    if sr not in (False, "off"):
        features.append("speculation_rules")

    return features


def check_csp_nonce(
    router: Router,
    config: Any,
    middleware_list: list[Any],
    discovered_routes: list[Any] | None = None,
) -> list[ContractIssue]:
    """Flag framework inline scripts blocked by a nonce-only CSP with no nonce.

    Every framework inline ``<script>`` is built through a per-request snippet
    factory (#195), so it carries the live nonce whenever a per-request nonce
    mechanism is active (``CSPNonceMiddleware`` or ``csp_nonce_enabled``). The
    genuinely un-nonceable case — flagged here — is an **inline-forbidding CSP in
    force with no nonce mechanism** while a framework inline-script feature is
    enabled. Then ``csp_nonce()`` returns ``""`` and the factories emit un-nonced
    scripts the browser silently blocks.

    Severity is env-aware (production ERROR, staging WARNING, development
    silent), mirroring ``rules_security_stack``.

    Stays silent when: no inline-forbidding policy is in force; or a nonce
    mechanism is active (everything is nonceable); or no inline-script feature is
    enabled.
    """
    issues: list[ContractIssue] = []

    # A per-request nonce mechanism makes every framework inline script nonceable.
    # ``csp_nonce_enabled`` auto-wires ``CSPNonceMiddleware`` at freeze time.
    nonce_enabled = bool(getattr(config, "csp_nonce_enabled", False))
    has_nonce_mw = any(type(mw).__name__ == _CSP_NONCE_MIDDLEWARE for mw in middleware_list)
    if nonce_enabled or has_nonce_mw:
        return issues

    # No nonce mechanism. Is an inline-forbidding policy in force? Only a static
    # CSP can forbid inline here (CSPNonceMiddleware was ruled out above).
    csp = _effective_csp(config, middleware_list)
    if csp is None or not _forbids_inline(csp):
        return issues

    # An inline-forbidding CSP with no nonce mechanism. Does the app actually
    # emit a framework inline script that would be blocked?
    features = _enabled_inline_script_features(config)
    if not features:
        return issues

    env = getattr(config, "env", "development")
    if env not in ("production", "staging"):
        return issues

    severity = Severity.ERROR if env == "production" else Severity.WARNING
    feature_list = ", ".join(features)
    issues.append(
        ContractIssue(
            severity=severity,
            category="csp_nonce",
            message=(
                f"App ships an inline-forbidding Content-Security-Policy (script-src "
                f"without 'unsafe-inline') but no per-request nonce mechanism, while "
                f"framework inline-script feature(s) are enabled ({feature_list}). "
                f"These inline <script> tags emit without a nonce and the browser will "
                f"silently block them (env='{env}'). Enable CSPNonceMiddleware "
                "(or AppConfig(csp_nonce_enabled=True), which auto-wires it) so the "
                "framework scripts carry the live per-request nonce; or, discouraged, "
                "add 'unsafe-inline' to script-src."
            ),
        )
    )

    return issues
