"""chirp-ui CSP contract check — the effective CSP must keep Alpine alive (#233).

chirp-ui drives its shell with Alpine: components evaluate expressions as JS
(needs ``script-src 'unsafe-eval'``) and toggle visibility via inline
``style="display:none"`` attributes that **cannot be nonced** (needs
``style-src 'unsafe-inline'``). If the effective Content-Security-Policy forbids
either, the entire interactive shell (collapse, dropdowns, theme toggle, command
palette, modals) silently dies in the browser — and because CORS masks
cross-origin script errors, there is no console error. That invisible failure is
the worst class, so this rule **fails loud** at ``app.check()`` time instead.

As of #233 ``use_chirp_ui(app)`` owns this: it flips ``csp_nonce_enabled=True``,
which makes the compiler wire ``CSPNonceMiddleware`` with ``'unsafe-eval'`` +
``style-src 'unsafe-inline'`` automatically — so a stock chirp-ui app passes this
check with **no hand-written CSP**. The rule exists to catch an app that pins its
own conflicting static CSP (e.g. a ``SecurityHeadersMiddleware`` whose
``script-src`` drops inline/``'unsafe-eval'`` *and* there is no nonce mechanism,
or whose ``style-src`` forbids inline style).

This rule runs **only when chirp-ui is active** (``extras["chirpui_components"]``
is set by ``use_chirp_ui`` at freeze). It is a no-op for non-chirp-ui apps so
they are unaffected.

Severity is env-aware, mirroring ``rules_security_stack`` / ``rules_csp_nonce``:
ERROR in production, WARNING in staging, **silent** in development (the default)
so dev apps and shipped examples stay clean.

The rule stays **silent** when:

- chirp-ui is not active, **or**
- a per-request nonce mechanism is active AND its style-src permits inline
  (the auto-wired path — everything Alpine needs is granted), **or**
- a static CSP is in force that already permits both inline script
  (``'unsafe-inline'`` or ``'unsafe-eval'`` for the eval surface) and inline style.

Detection follows the sibling rules: middleware is matched by class **name**
(``type(mw).__name__``) so this layer never imports middleware classes. The
``@alpinejs/csp`` build (``alpine_csp=True``) avoids ``eval`` and the inline
bootstrap, but chirp-ui's shipped components still emit inline ``@click``/
``x-show``/``:class`` and the modal ``x-data`` factory call, so it is **not**
treated as exempt here — chirp-ui needs the standard build's relaxations.
"""

from typing import TYPE_CHECKING, Any

from chirp.contracts.rules_csp_nonce import _forbids_inline, _script_src_directive
from chirp.contracts.types import ContractIssue, Severity

if TYPE_CHECKING:
    from chirp.routing.router import Router

_SECURITY_HEADERS_MIDDLEWARE = "SecurityHeadersMiddleware"
_CSP_NONCE_MIDDLEWARE = "CSPNonceMiddleware"


def _style_src_directive(csp: str) -> str | None:
    """Return the ``style-src`` directive value from a CSP string, or None.

    Falls back to ``default-src`` per the CSP spec when ``style-src`` is absent.
    """
    src: str | None = None
    default: str | None = None
    for directive in csp.split(";"):
        directive = directive.strip()
        if not directive:
            continue
        name, _, value = directive.partition(" ")
        name = name.lower()
        if name == "style-src":
            src = value.strip()
        elif name == "default-src":
            default = value.strip()
    return src if src is not None else default


def _style_forbids_inline(csp: str) -> bool:
    """True when the effective style-src forbids inline ``style=`` attributes.

    A CSP forbids inline style when a ``style-src`` (or fallback ``default-src``)
    is present and does *not* list ``'unsafe-inline'``. Alpine's ``x-show`` writes
    inline style attributes that cannot be nonced, so this is fatal for chirp-ui.
    """
    directive = _style_src_directive(csp)
    if directive is None:
        return False
    return "'unsafe-inline'" not in directive


def _script_allows_alpine(csp: str) -> bool:
    """True when the script-src permits Alpine's inline bootstrap + eval.

    Alpine needs inline script execution: either ``'unsafe-inline'`` (covers the
    bootstrap) or, under a nonce policy, the bootstrap is nonced — but it still
    needs ``'unsafe-eval'`` for expression evaluation. This helper answers "does a
    *static* CSP grant what Alpine needs without a nonce mechanism", so it
    requires ``'unsafe-inline'`` (un-nonced inline) AND ``'unsafe-eval'``.
    """
    directive = _script_src_directive(csp)
    if directive is None:
        # No script-src and no default-src: nothing forbidden.
        return True
    return "'unsafe-inline'" in directive and "'unsafe-eval'" in directive


def _static_csp(middleware_list: list[Any], config: Any) -> str | None:
    """Resolve the static CSP string the app will actually send, or None.

    Mirrors ``rules_csp_nonce._effective_csp``: an explicit
    ``SecurityHeadersMiddleware`` config wins; otherwise the app-level
    ``content_security_policy`` fallback. The dynamic ``CSPNonceMiddleware`` CSP
    is detected separately (it is always nonce-bearing + Alpine-aware by
    construction once chirp-ui flips the flag).
    """
    for mw in middleware_list:
        if type(mw).__name__ != _SECURITY_HEADERS_MIDDLEWARE:
            continue
        cfg = getattr(mw, "config", None)
        csp = getattr(cfg, "content_security_policy", None)
        if csp:
            return csp
    return getattr(config, "content_security_policy", None)


def check_chirpui_csp(
    router: Router,
    config: Any,
    middleware_list: list[Any],
    extras: dict[str, Any] | None = None,
) -> list[ContractIssue]:
    """Flag a chirp-ui app whose effective CSP would kill Alpine.

    No-op unless chirp-ui is active (``extras["chirpui_components"]`` set by
    ``use_chirp_ui``). When active, validates the EFFECTIVE CSP the app will send:

    - script-src must allow Alpine's inline bootstrap + eval (via a nonce
      mechanism — auto-wired by ``csp_nonce_enabled`` — or static
      ``'unsafe-inline'`` + ``'unsafe-eval'``);
    - style-src must allow inline style (Alpine ``x-show`` is un-nonceable).

    Severity is env-aware (production ERROR, staging WARNING, development silent),
    mirroring ``rules_security_stack`` / ``rules_csp_nonce``.
    """
    issues: list[ContractIssue] = []

    # No-op when chirp-ui is not active so non-chirp-ui apps are unaffected.
    if not (extras or {}).get("chirpui_components"):
        return issues

    env = getattr(config, "env", "development")
    if env not in ("production", "staging"):
        return issues

    # A per-request nonce mechanism (csp_nonce_enabled / CSPNonceMiddleware) means
    # the compiler granted Alpine its 'unsafe-eval' + style-src 'unsafe-inline'
    # (compiler.py wires both for alpine + not alpine_csp). That covers the
    # auto-wired chirp-ui path. But the app could *also* pin a static
    # SecurityHeadersMiddleware CSP that overrides it — so we still inspect the
    # static CSP below: if one is in force and it forbids what Alpine needs, the
    # later header wins and Alpine dies.
    nonce_enabled = bool(getattr(config, "csp_nonce_enabled", False))
    has_nonce_mw = any(type(mw).__name__ == _CSP_NONCE_MIDDLEWARE for mw in middleware_list)
    nonce_path = nonce_enabled or has_nonce_mw

    static_csp = _static_csp(middleware_list, config)

    broken: list[str] = []
    if static_csp is not None:
        # An explicit static CSP is in force. It is the policy the browser sees
        # (a static SecurityHeadersMiddleware header overrides the nonce header
        # when both are present), so validate it directly.
        if _forbids_inline(static_csp) and not _script_allows_alpine(static_csp):
            broken.append("script-src forbids Alpine's inline bootstrap/eval")
        if _style_forbids_inline(static_csp):
            broken.append("style-src forbids inline style (Alpine x-show)")
    elif not nonce_path:
        # No static CSP and no nonce mechanism. The default SecurityHeaders CSP
        # (if a bare SecurityHeadersMiddleware is added) omits both relaxations,
        # and without the nonce path nothing grants them — Alpine is dead.
        broken.append("no nonce mechanism and no Alpine-compatible CSP in force")

    if not broken:
        return issues

    severity = Severity.ERROR if env == "production" else Severity.WARNING
    reasons = "; ".join(broken)
    issues.append(
        ContractIssue(
            severity=severity,
            category="chirpui_csp",
            message=(
                f"chirp-ui is active but the effective Content-Security-Policy would "
                f"silently kill Alpine ({reasons}). chirp-ui's shell evaluates Alpine "
                f"expressions as JS (needs script-src 'unsafe-eval') and toggles "
                f"visibility via inline style attributes that cannot be nonced (needs "
                f"style-src 'unsafe-inline'); a forbidding policy breaks collapse, "
                f"dropdowns, the theme toggle, modals, and the command palette with no "
                f"console error (CORS masks it). Remove the conflicting static CSP and "
                f"let use_chirp_ui's auto-wired per-request nonce CSP own the header "
                f"(csp_nonce_enabled, set automatically), or relax script-src/style-src "
                f"to match Alpine's needs (env='{env}')."
            ),
        )
    )

    return issues
