"""CSP-nonce contract rule (#181, #195).

Unit tests over a stub router + AppConfig + stub middleware, mirroring
test_security_stack_rule.py.

As of #195 every framework inline ``<script>`` is built through a per-request
snippet factory, so it carries the live nonce whenever a per-request nonce
mechanism is active (``CSPNonceMiddleware`` / ``csp_nonce_enabled``). The rule
ERRORs (env-aware) only on the genuinely un-nonceable case: an inline-forbidding
CSP in force with **no** nonce mechanism, while a framework inline-script feature
is enabled. These tests assert both the firing case (with a negative control
proving the test is not vacuous) and every silent case.
"""

from chirp.config import AppConfig
from chirp.contracts.rules_csp_nonce import (
    _enabled_inline_script_features,
    _forbids_inline,
    _script_src_directive,
    check_csp_nonce,
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
# Feature detection
# ---------------------------------------------------------------------------


def test_features_include_defaults_safe_target_and_sse_lifecycle():
    # safe_target and sse_lifecycle default to True.
    features = _enabled_inline_script_features(AppConfig())
    assert "safe_target" in features
    assert "sse_lifecycle" in features


def test_features_alpine_counted_only_without_csp_build():
    assert "alpine" in _enabled_inline_script_features(AppConfig(alpine=True))
    assert "alpine" not in _enabled_inline_script_features(AppConfig(alpine=True, alpine_csp=True))


def test_features_view_transitions_counted_for_non_off_modes():
    assert "view_transitions" not in _enabled_inline_script_features(
        AppConfig(view_transitions=False)
    )
    assert "view_transitions" in _enabled_inline_script_features(AppConfig(view_transitions=True))
    assert "view_transitions" in _enabled_inline_script_features(AppConfig(view_transitions="full"))


def test_features_empty_when_all_inline_features_disabled():
    config = AppConfig(safe_target=False, sse_lifecycle=False)
    assert _enabled_inline_script_features(config) == []


# ---------------------------------------------------------------------------
# Rule fires on the genuinely un-nonceable case (env-aware)
# ---------------------------------------------------------------------------


def test_fires_in_production_with_forbidding_csp_no_nonce_mechanism():
    """Static nonce-only CSP, no CSPNonceMiddleware, no csp_nonce_enabled, and a
    framework inline-script feature is enabled -> ERROR in production.

    Negative control: see ``test_negative_control_no_features_silent`` — with
    every inline feature disabled the same config stays silent, proving this
    assertion is driven by the feature gate, not vacuously true.
    """
    config = AppConfig(env="production", secret_key="x" * 32, alpine=True)
    issues = check_csp_nonce(_Router(), config, [SecurityHeadersMiddleware(_NONCE_CSP)])
    assert len(issues) == 1
    assert issues[0].severity is Severity.ERROR
    assert issues[0].category == "csp_nonce"
    assert "CSPNonceMiddleware" in issues[0].message


def test_fires_warning_in_staging():
    config = AppConfig(env="staging", secret_key="x" * 32, alpine=True)
    issues = check_csp_nonce(_Router(), config, [SecurityHeadersMiddleware(_NONCE_CSP)])
    assert len(issues) == 1
    assert issues[0].severity is Severity.WARNING


def test_fires_on_default_features_alone_without_alpine():
    """Even without Alpine, the default safe_target/sse_lifecycle scripts trip it."""
    config = AppConfig(env="production", secret_key="x" * 32, alpine=False)
    issues = check_csp_nonce(_Router(), config, [SecurityHeadersMiddleware(_NONCE_CSP)])
    assert len(issues) == 1
    assert issues[0].severity is Severity.ERROR


class _StubConfig:
    """Minimal config exposing the attributes ``check_csp_nonce`` reads, plus
    ``content_security_policy`` (which lives on SecurityHeadersConfig, not the
    real AppConfig — the rule reads it via getattr for the app-level fallback)."""

    def __init__(self, **kw):
        self.env = kw.get("env", "development")
        self.csp_nonce_enabled = kw.get("csp_nonce_enabled", False)
        self.alpine = kw.get("alpine", False)
        self.alpine_csp = kw.get("alpine_csp", False)
        self.safe_target = kw.get("safe_target", False)
        self.sse_lifecycle = kw.get("sse_lifecycle", False)
        self.delegation = kw.get("delegation", False)
        self.islands = kw.get("islands", False)
        self.view_transitions = kw.get("view_transitions", False)
        self.speculation_rules = kw.get("speculation_rules", False)
        self.content_security_policy = kw.get("content_security_policy")


def test_fires_when_csp_from_app_config():
    """The forbidding CSP can come from config.content_security_policy too."""
    config = _StubConfig(env="production", alpine=True, content_security_policy=_NONCE_CSP)
    issues = check_csp_nonce(_Router(), config, [])
    assert len(issues) == 1
    assert issues[0].severity is Severity.ERROR


# ---------------------------------------------------------------------------
# Negative control — the firing assertion is not vacuous
# ---------------------------------------------------------------------------


def test_negative_control_no_features_silent():
    """Same forbidding CSP + no nonce mechanism, but EVERY inline-script feature
    disabled -> silent. Proves the firing tests are driven by the feature gate.
    """
    config = AppConfig(
        env="production", secret_key="x" * 32, safe_target=False, sse_lifecycle=False
    )
    issues = check_csp_nonce(_Router(), config, [SecurityHeadersMiddleware(_NONCE_CSP)])
    assert issues == []


# ---------------------------------------------------------------------------
# Silent cases
# ---------------------------------------------------------------------------


def test_silent_in_development():
    """Development env is silent so dev apps and shipped examples stay clean."""
    config = AppConfig(env="development", alpine=True)
    issues = check_csp_nonce(_Router(), config, [SecurityHeadersMiddleware(_NONCE_CSP)])
    assert issues == []


def test_silent_with_csp_nonce_middleware():
    """A nonce mechanism makes every inline script nonceable -> silent even with
    alpine + the default features and a forbidding CSP."""
    config = AppConfig(env="production", secret_key="x" * 32, alpine=True)
    issues = check_csp_nonce(
        _Router(),
        config,
        [SecurityHeadersMiddleware(_NONCE_CSP), CSPNonceMiddleware()],
    )
    assert issues == []


def test_silent_with_csp_nonce_enabled_config():
    """csp_nonce_enabled auto-wires CSPNonceMiddleware -> silent."""
    config = AppConfig(env="production", secret_key="x" * 32, alpine=True, csp_nonce_enabled=True)
    issues = check_csp_nonce(_Router(), config, [SecurityHeadersMiddleware(_NONCE_CSP)])
    assert issues == []


def test_silent_under_inline_allowing_csp():
    """An inline-allowing CSP ('unsafe-inline' present) is not forbidding."""
    config = AppConfig(env="production", secret_key="x" * 32, alpine=True)
    issues = check_csp_nonce(_Router(), config, [SecurityHeadersMiddleware(_INLINE_CSP)])
    assert issues == []


def test_silent_when_no_csp_at_all():
    """No forbidding policy -> nothing to block."""
    config = AppConfig(env="production", secret_key="x" * 32, alpine=True)
    assert check_csp_nonce(_Router(), config, []) == []


def test_silent_alpine_csp_build_unaffected():
    """The @alpinejs/csp build ships no inline bootstrap. With only the CSP build
    and no other inline features, the rule stays silent under a nonce policy."""
    config = AppConfig(
        env="production",
        secret_key="x" * 32,
        alpine=True,
        alpine_csp=True,
        safe_target=False,
        sse_lifecycle=False,
    )
    issues = check_csp_nonce(_Router(), config, [SecurityHeadersMiddleware(_NONCE_CSP)])
    assert issues == []
