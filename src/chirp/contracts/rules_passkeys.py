"""Passkeys / WebAuthn startup contract — env-aware posture for ``passkeys=True``.

Two passkeys-specific checks fire when ``AppConfig(passkeys=True)``. What this
rule deliberately does **not** re-check (to stay non-redundant and low-noise):
the generic "a mutating route needs Session/CSRF" presence check is owned by
``rules_security_stack`` (a passkeys app's finish endpoints are mutating POSTs,
so that rule already requires ``SessionMiddleware``); the static
"rp_id is a registrable suffix of origin" invariant is owned by
``PasskeyConfig.__post_init__`` (fail-loud at construction); and the
HTTPS-in-production posture is covered by ``rules_cookie_secure`` (a Secure
session cookie implies HTTPS, which is WebAuthn's secure-context requirement).

- ``passkeys`` **ERROR (env-INDEPENDENT)**: ``passkeys=True`` but the ``webauthn``
  package is not importable. Passkeys cannot work without it in *any*
  environment — every ceremony raises ``ConfigurationError`` at runtime — so this
  is a broken config, not a hardening gap, and is reported regardless of ``env``
  (mirroring the env-independent ``samesite='none'`` cookie-drop ERROR in
  ``rules_cookie_secure``). ``webauthn`` availability is read via
  ``chirp.security.passkeys._has_webauthn`` — the same find-spec probe the runtime
  uses to fail loud — not a middleware class name (mirrors how
  ``rules_password_extra`` reads ``_has_argon2``).

- ``passkeys`` **WARNING (env-aware: production/staging, silent in development)**:
  ``passkeys=True`` with a ``CookieSessionStore``. The single-use WebAuthn
  challenge is stashed in the session between begin and finish; the cookie store
  signs the *entire* session (incl. the ~86-char base64url challenge) into the
  client cookie, whereas ``RedisSessionStore`` strips ``__``-prefixed keys from
  durable storage. The challenge is popped on finish, but abandoned begin-flows
  carry it until session timeout. Advisory only — mirrors ``rules_password_extra``'s
  env-aware WARNING (silent in dev). The ``CookieSessionStore`` detection uses
  class-name detection (``type(store).__name__``), per the contracts-layer
  convention (never import middleware/stores into ``contracts/``).

Built-in (not a plugin ``ContractCheck``) because it reads ``config`` (the
passkeys flag + ``env``) and ``middleware_list`` (the session store), which the
plugin ``ContractCheckSnapshot`` does not expose — the same reason the chirp-ui
CSP rule is built-in (see ``contracts/AGENTS.md``).
"""

from typing import Any

from chirp.contracts.types import ContractIssue, Severity

# Detected by class NAME (see module docstring) — no middleware/store import.
_SESSION_MIDDLEWARE = "SessionMiddleware"
_COOKIE_STORE = "CookieSessionStore"


def check_passkeys(config: Any, middleware_list: list[Any]) -> list[ContractIssue]:
    """Flag a broken or sub-optimal ``passkeys=True`` posture.

    No-op unless ``AppConfig.passkeys`` is truthy.
    """
    issues: list[ContractIssue] = []

    if not getattr(config, "passkeys", False):
        return issues

    # 1. Hard dependency — env-independent ERROR. Lazy import keeps the contracts
    #    layer importable without chirp.security.passkeys / webauthn present.
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

    # 2. Cookie-store challenge bloat — env-aware advisory WARNING (silent dev).
    env = getattr(config, "env", "development")
    if env in ("production", "staging"):
        for mw in middleware_list:
            if type(mw).__name__ != _SESSION_MIDDLEWARE:
                continue
            store = getattr(mw, "_store", None)
            if store is not None and type(store).__name__ == _COOKIE_STORE:
                issues.append(
                    ContractIssue(
                        severity=Severity.WARNING,
                        category="passkeys",
                        message=(
                            "passkeys=True with a CookieSessionStore: the single-use "
                            "WebAuthn challenge is stored in the session between begin "
                            "and finish, and the cookie store signs the entire session "
                            "(including the ~86-char challenge) into the client cookie. "
                            "It is popped on finish, but abandoned begin-flows carry it "
                            "until session timeout. For passkey-heavy traffic prefer "
                            "RedisSessionStore (strips __-prefixed keys from storage) or "
                            "set a short SessionConfig(absolute_timeout_seconds=...)."
                        ),
                    )
                )
                break  # one nudge is enough

    return issues
