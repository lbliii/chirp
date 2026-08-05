"""Passkeys / WebAuthn startup contract — ``passkeys=True`` dependency posture.

What this rule deliberately does **not** re-check (to stay non-redundant and
low-noise): the generic "a mutating route needs Session/CSRF" presence check is
owned by ``rules_security_stack`` (a passkeys app's finish endpoints are
mutating POSTs, so that rule already requires ``SessionMiddleware``); the
static "rp_id is a registrable suffix of origin" invariant is owned by
``PasskeyConfig.__post_init__`` (fail-loud at construction); and the
HTTPS-in-production posture is covered by ``rules_cookie_secure`` (a Secure
session cookie implies HTTPS, which is WebAuthn's secure-context requirement).

Cookie-backed sessions are a first-class production path for passkeys. The
single-use challenge (~86-char base64url) lives in the session between begin
and finish on both ``CookieSessionStore`` and ``RedisSessionStore``; Redis is
optional for horizontal scaling, not required for ceremonies (#871).

- ``passkeys`` **ERROR (env-INDEPENDENT)**: ``passkeys=True`` but the ``webauthn``
  package is not importable. Passkeys cannot work without it in *any*
  environment — every ceremony raises ``ConfigurationError`` at runtime — so this
  is a broken config, not a hardening gap, and is reported regardless of ``env``
  (mirroring the env-independent ``samesite='none'`` cookie-drop ERROR in
  ``rules_cookie_secure``). ``webauthn`` availability is read via
  ``chirp.security.passkeys._has_webauthn`` — the same find-spec probe the runtime
  uses to fail loud — not a middleware class name (mirrors how
  ``rules_password_extra`` reads ``_has_argon2``).

Built-in (not a plugin ``ContractCheck``) because it reads ``config`` (the
passkeys flag), which the plugin ``ContractCheckSnapshot`` does not expose —
the same reason the chirp-ui CSP rule is built-in (see ``contracts/AGENTS.md``).
"""

from typing import Any

from chirp.contracts.types import ContractIssue, Severity


def check_passkeys(config: Any, _middleware_list: list[Any]) -> list[ContractIssue]:
    """Flag a broken ``passkeys=True`` posture (missing ``webauthn``).

    No-op unless ``AppConfig.passkeys`` is truthy. ``_middleware_list`` is
    accepted for call-site parity with other built-in rules; unused since cookie
    sessions are first-class and no longer trigger a Redis-preferring WARNING
    (#871).
    """
    issues: list[ContractIssue] = []

    if not getattr(config, "passkeys", False):
        return issues

    # Hard dependency — env-independent ERROR. Lazy import keeps the contracts
    # layer importable without chirp.security.passkeys / webauthn present.
    from chirp.security.passkeys import _has_webauthn

    if not _has_webauthn():
        issues.append(
            ContractIssue(
                severity=Severity.ERROR,
                category="passkeys",
                message=(
                    "AppConfig(passkeys=True) but the 'webauthn' package is not "
                    "installed, so every passkey ceremony will fail at runtime. "
                    "Install it with: pip install chirp[passkeys]"
                ),
            )
        )

    return issues
