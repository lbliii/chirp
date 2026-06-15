"""chirp-ui CSP contract rule (#233).

Unit tests over a stub router + AppConfig + stub middleware, mirroring
test_csp_nonce_rule.py.

``use_chirp_ui(app)`` (since #233) flips ``csp_nonce_enabled=True``, which makes
the compiler wire ``CSPNonceMiddleware`` with ``'unsafe-eval'`` + style-src
``'unsafe-inline'`` — exactly what chirp-ui's Alpine shell needs. This rule fires
(env-aware) only when chirp-ui is active AND the *effective* CSP would still kill
Alpine: a conflicting static CSP that forbids the inline bootstrap/eval or inline
style. These tests assert the firing cases (with a negative control proving they
are not vacuous) and every silent case.
"""

import pytest

from chirp.config import AppConfig
from chirp.contracts.rules_chirpui_csp import (
    _script_allows_alpine,
    _style_forbids_inline,
    _style_src_directive,
    check_chirpui_csp,
)
from chirp.contracts.types import Severity


class _Router:
    def __init__(self, routes=None):
        self.routes = routes or []


# Detection is by class NAME, so these names matter.
class SecurityHeadersMiddleware:
    def __init__(self, csp):
        self.config = _SecCfg(csp)


class CSPNonceMiddleware:
    pass


class _SecCfg:
    def __init__(self, csp):
        self.content_security_policy = csp


# chirp-ui active marker (set by use_chirp_ui at freeze).
_UI = {"chirpui_components": frozenset({"card.html", "modal.html"})}

# A restrictive CSP that forbids inline script and inline style.
_RESTRICTIVE = "default-src 'self'; script-src 'self'"
# An Alpine-compatible static CSP (no nonce mechanism needed).
_ALPINE_OK = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-eval' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'"
)


# ---------------------------------------------------------------------------
# Parser helpers
# ---------------------------------------------------------------------------


def test_style_src_directive_extracted():
    assert _style_src_directive("style-src 'self' 'unsafe-inline'") == "'self' 'unsafe-inline'"


def test_style_src_falls_back_to_default_src():
    assert _style_src_directive("default-src 'self'") == "'self'"


def test_style_forbids_inline_true_when_no_unsafe_inline():
    assert _style_forbids_inline(_RESTRICTIVE) is True


def test_style_forbids_inline_false_when_unsafe_inline_present():
    assert _style_forbids_inline("style-src 'self' 'unsafe-inline'") is False


def test_style_forbids_inline_false_when_no_directive():
    assert _style_forbids_inline("frame-ancestors 'none'") is False


def test_script_allows_alpine_requires_both_unsafe():
    assert _script_allows_alpine("script-src 'self' 'unsafe-eval' 'unsafe-inline'") is True
    assert _script_allows_alpine("script-src 'self' 'unsafe-inline'") is False  # no eval
    assert _script_allows_alpine("script-src 'self' 'unsafe-eval'") is False  # no inline


def test_script_allows_alpine_true_when_no_directive():
    assert _script_allows_alpine("frame-ancestors 'none'") is True


# ---------------------------------------------------------------------------
# No-op unless chirp-ui is active
# ---------------------------------------------------------------------------


@pytest.mark.issue(233)
def test_silent_when_chirpui_not_active():
    """A non-chirp-ui app is unaffected even with a restrictive CSP in production."""
    config = AppConfig(env="production", secret_key="x" * 32, alpine=True)
    issues = check_chirpui_csp(
        _Router(), config, [SecurityHeadersMiddleware(_RESTRICTIVE)], extras={}
    )
    assert issues == []


# ---------------------------------------------------------------------------
# Rule fires when chirp-ui is active and the effective CSP kills Alpine
# ---------------------------------------------------------------------------


@pytest.mark.issue(233)
def test_fires_error_in_production_with_conflicting_static_csp():
    """chirp-ui active + a static CSP that forbids inline script and inline style
    -> ERROR in production, even though csp_nonce_enabled is on (the static header
    overrides the nonce header).

    Negative control: ``test_silent_when_chirpui_not_active`` proves the firing is
    driven by the chirp-ui gate, not vacuously true.
    """
    config = AppConfig(env="production", secret_key="x" * 32, alpine=True, csp_nonce_enabled=True)
    issues = check_chirpui_csp(
        _Router(), config, [SecurityHeadersMiddleware(_RESTRICTIVE)], extras=_UI
    )
    assert len(issues) == 1
    assert issues[0].severity is Severity.ERROR
    assert issues[0].category == "chirpui_csp"
    assert "Alpine" in issues[0].message


@pytest.mark.issue(233)
def test_fires_warning_in_staging():
    config = AppConfig(env="staging", secret_key="x" * 32, alpine=True, csp_nonce_enabled=True)
    issues = check_chirpui_csp(
        _Router(), config, [SecurityHeadersMiddleware(_RESTRICTIVE)], extras=_UI
    )
    assert len(issues) == 1
    assert issues[0].severity is Severity.WARNING


@pytest.mark.issue(233)
def test_fires_when_style_src_forbids_inline_only():
    """script-src is fine (nonce + unsafe-eval), but style-src forbids inline ->
    Alpine x-show dies. Must still fire."""
    csp = "default-src 'self'; script-src 'self' 'unsafe-eval' 'unsafe-inline'; style-src 'self'"
    config = AppConfig(env="production", secret_key="x" * 32, alpine=True)
    issues = check_chirpui_csp(_Router(), config, [SecurityHeadersMiddleware(csp)], extras=_UI)
    assert len(issues) == 1
    assert "style-src" in issues[0].message


@pytest.mark.issue(233)
def test_fires_when_no_nonce_mechanism_and_no_csp():
    """chirp-ui active, no nonce mechanism, no static CSP — a bare default
    SecurityHeaders CSP would forbid both. Fires in production."""
    config = AppConfig(env="production", secret_key="x" * 32, alpine=True, csp_nonce_enabled=False)
    issues = check_chirpui_csp(_Router(), config, [], extras=_UI)
    assert len(issues) == 1
    assert issues[0].severity is Severity.ERROR


# ---------------------------------------------------------------------------
# Silent cases
# ---------------------------------------------------------------------------


@pytest.mark.issue(233)
def test_silent_in_development():
    """Development env stays silent so shipped examples and dev apps stay clean."""
    config = AppConfig(env="development", alpine=True, csp_nonce_enabled=True)
    issues = check_chirpui_csp(
        _Router(), config, [SecurityHeadersMiddleware(_RESTRICTIVE)], extras=_UI
    )
    assert issues == []


@pytest.mark.issue(233)
def test_silent_on_auto_wired_nonce_path():
    """The stock chirp-ui path: csp_nonce_enabled on, no conflicting static CSP.
    The compiler grants unsafe-eval + style-src unsafe-inline -> silent."""
    config = AppConfig(env="production", secret_key="x" * 32, alpine=True, csp_nonce_enabled=True)
    issues = check_chirpui_csp(_Router(), config, [], extras=_UI)
    assert issues == []


@pytest.mark.issue(233)
def test_silent_with_alpine_compatible_static_csp():
    """A hand-written CSP that already permits Alpine's needs -> silent."""
    config = AppConfig(env="production", secret_key="x" * 32, alpine=True)
    issues = check_chirpui_csp(
        _Router(), config, [SecurityHeadersMiddleware(_ALPINE_OK)], extras=_UI
    )
    assert issues == []


@pytest.mark.issue(233)
def test_silent_with_bare_security_headers_and_nonce_path():
    """SecurityHeaders with content_security_policy=None (no CSP header) + the
    auto-wired nonce path is the lucky_cat idiom -> silent."""
    config = AppConfig(env="production", secret_key="x" * 32, alpine=True, csp_nonce_enabled=True)
    issues = check_chirpui_csp(_Router(), config, [SecurityHeadersMiddleware(None)], extras=_UI)
    assert issues == []
