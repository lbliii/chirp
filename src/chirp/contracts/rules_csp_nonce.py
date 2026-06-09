"""CSP-nonce contract check — framework inline scripts must be nonceable (#181).

When an app ships a **nonce-based / inline-forbidding** Content-Security-Policy
(a ``script-src`` that does *not* include ``'unsafe-inline'``), every inline
``<script>`` the framework emits must carry a live ``nonce`` attribute or it is
silently blocked by the browser.

Two framework inline-script surfaces exist:

1. **Suspense initial-load scripts** (``format_oob_script``): these now capture
   the live request nonce inside ``render_suspense`` and stream it through, so
   they survive a nonce-only CSP. This is the lifecycle fix in #181.

2. **Alpine ``safeData`` helper** (``safe_data_helper`` inside ``alpine_snippet``):
   this snippet is precomputed at app-compile time by ``AlpineInject`` — *outside*
   any request scope — so it cannot carry a per-request nonce. Under a nonce-only
   CSP this inline script is blocked and **all** Alpine components die silently.

This check ERRORs on case (2): an app that enables ``alpine=True`` together with
a nonce-based CSP that forbids inline scripts, because the Alpine bootstrap
inline script cannot be nonced through the precompiled injection path. The fix
is to either keep ``'unsafe-inline'`` is *not* the answer (defeats the nonce);
the supported escape hatch is ``alpine_csp=True`` (the CSP build needs no inline
bootstrap of that shape) — but the canonical signal is that a regression dropped
the nonce path for a framework emitter.

Detection follows ``rules_security_stack``: middleware is matched by class
**name** (``type(mw).__name__``) so this layer never imports middleware classes.
The CSP string is read from ``SecurityHeadersMiddleware`` config or
``config.content_security_policy`` and parsed for an inline-forbidding
``script-src``.

This check stays **silent** when CSP nonces are disabled and no inline-forbidding
CSP is configured, so nonce-unaware apps and shipped examples stay clean. It does
not double-fire with ``security_stack`` (which is about CSRF/Session presence) or
``csrf_session`` (stack ordering).
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
    """Resolve the CSP string the app will actually send.

    Order of precedence mirrors how responses are built: an explicit
    ``SecurityHeadersMiddleware`` config wins; otherwise the app-level
    ``content_security_policy`` (if any). The dynamic per-request nonce CSP from
    ``CSPNonceMiddleware`` is nonce-bearing by construction (it injects
    ``'nonce-...'`` and no ``'unsafe-inline'``) and is treated as inline-forbidding
    too, so its presence alone signals a nonce policy.
    """
    for mw in middleware_list:
        if type(mw).__name__ != _SECURITY_HEADERS_MIDDLEWARE:
            continue
        cfg = getattr(mw, "config", None)
        csp = getattr(cfg, "content_security_policy", None)
        if csp:
            return csp
    return getattr(config, "content_security_policy", None)


def check_csp_nonce(
    router: Router,
    config: Any,
    middleware_list: list[Any],
    discovered_routes: list[Any] | None = None,
) -> list[ContractIssue]:
    """Flag framework inline scripts that would be blocked by a nonce-only CSP.

    ERRORs when the app emits the Alpine ``safeData`` bootstrap inline script
    (``alpine=True``) while shipping an inline-forbidding CSP (a ``script-src``
    without ``'unsafe-inline'``), because that precomputed inline script cannot
    carry a per-request nonce and Alpine silently dies in the browser.

    Stays silent when:

    - The app ships no inline-forbidding CSP (no nonce policy) **and** does not
      enable ``csp_nonce_enabled`` — i.e. nonce-unaware apps.
    - Alpine is not enabled (no framework inline bootstrap to block), or the
      ``alpine_csp`` build is used (no inline bootstrap of the blocked shape).
    """
    issues: list[ContractIssue] = []

    alpine_on = bool(getattr(config, "alpine", False))
    alpine_csp = bool(getattr(config, "alpine_csp", False))
    nonce_enabled = bool(getattr(config, "csp_nonce_enabled", False))

    csp = _effective_csp(config, middleware_list)
    has_nonce_mw = any(type(mw).__name__ == _CSP_NONCE_MIDDLEWARE for mw in middleware_list)

    # An inline-forbidding policy is in force when either a static CSP forbids
    # inline, or a nonce policy is active (CSPNonceMiddleware / csp_nonce_enabled
    # both yield a nonce-only script-src with no 'unsafe-inline').
    inline_forbidden = (csp is not None and _forbids_inline(csp)) or has_nonce_mw or nonce_enabled

    if not inline_forbidden:
        return issues

    # Alpine bootstrap inline script is precomputed by AlpineInject (outside
    # request scope) and cannot be nonced. The csp build avoids the inline
    # bootstrap shape, so it is exempt.
    if alpine_on and not alpine_csp:
        issues.append(
            ContractIssue(
                severity=Severity.ERROR,
                category="csp_nonce",
                message=(
                    "App enables Alpine.js (alpine=True) under an inline-forbidding "
                    "Content-Security-Policy (script-src has no 'unsafe-inline'), but "
                    "the Alpine safeData bootstrap is an inline <script> injected at "
                    "compile time and cannot carry a per-request nonce. It will be "
                    "blocked by the browser and every Alpine component will silently "
                    "fail. Use alpine_csp=True (the @alpinejs/csp build needs no "
                    "inline bootstrap) or relax the CSP."
                ),
            )
        )

    return issues
