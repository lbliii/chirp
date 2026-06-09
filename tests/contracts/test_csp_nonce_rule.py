"""CSP-nonce contract rule (#181).

Unit tests over a stub router + AppConfig + stub middleware, mirroring
test_security_stack_rule.py. Asserts the rule ERRORs when a framework inline
script (the Alpine bootstrap) would be blocked by an inline-forbidding CSP, and
stays silent otherwise.
"""

from chirp.config import AppConfig
from chirp.contracts.rules_csp_nonce import (
    _forbids_inline,
    _script_src_directive,
    check_csp_nonce,
)


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


_NONCE_CSP = "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net"
_INLINE_CSP = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net"


# ---------------------------------------------------------------------------
# Parser helpers
# ---------------------------------------------------------------------------


def test_script_src_directive_extracted():
    assert _script_src_directive(_NONCE_CSP) == "'self' https://cdn.jsdelivr.net"


def test_script_src_falls_back_to_default_src():
    assert _script_src_directive("default-src 'self'") == "'self'"


def test_forbids_inline_true_for_nonce_csp():
    assert _forbids_inline(_NONCE_CSP) is True


def test_forbids_inline_false_for_inline_csp():
    assert _forbids_inline(_INLINE_CSP) is False


def test_forbids_inline_false_when_no_directive():
    assert _forbids_inline("frame-ancestors 'none'") is False


# ---------------------------------------------------------------------------
# Rule behavior
# ---------------------------------------------------------------------------


def test_errors_alpine_under_nonce_csp():
    config = AppConfig(alpine=True)
    issues = check_csp_nonce(_Router(), config, [SecurityHeadersMiddleware(_NONCE_CSP)])
    assert len(issues) == 1
    assert issues[0].category == "csp_nonce"
    assert issues[0].severity.name == "ERROR"


def test_silent_alpine_under_inline_allowing_csp():
    config = AppConfig(alpine=True)
    issues = check_csp_nonce(_Router(), config, [SecurityHeadersMiddleware(_INLINE_CSP)])
    assert issues == []


def test_silent_when_alpine_disabled():
    config = AppConfig(alpine=False)
    issues = check_csp_nonce(_Router(), config, [SecurityHeadersMiddleware(_NONCE_CSP)])
    assert issues == []


def test_silent_when_alpine_csp_build():
    """The @alpinejs/csp build has no inline bootstrap of the blocked shape."""
    config = AppConfig(alpine=True, alpine_csp=True)
    issues = check_csp_nonce(_Router(), config, [SecurityHeadersMiddleware(_NONCE_CSP)])
    assert issues == []


def test_errors_alpine_with_csp_nonce_middleware():
    """CSPNonceMiddleware yields a nonce-only (inline-forbidding) policy."""
    config = AppConfig(alpine=True)
    issues = check_csp_nonce(_Router(), config, [CSPNonceMiddleware()])
    assert len(issues) == 1
    assert issues[0].category == "csp_nonce"


def test_errors_alpine_with_csp_nonce_enabled_config():
    config = AppConfig(alpine=True, csp_nonce_enabled=True)
    issues = check_csp_nonce(_Router(), config, [])
    assert len(issues) == 1


def test_silent_no_policy_no_alpine():
    config = AppConfig()
    assert check_csp_nonce(_Router(), config, []) == []
