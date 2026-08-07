"""Password-hashing deploy-posture check — argon2 in production (#220).

A single env-aware ADVISORY rule: when an app exposes a login / mutating surface
but ``argon2-cffi`` is **not** importable, the password-hashing path silently
falls back to stdlib scrypt. scrypt is a correct, always-available fallback (no
hash is ever rejected), but argon2id is the recommended algorithm for new
production deployments. This rule nudges toward ``pip install chirp[auth]`` in
production without breaking dev or scrypt-only CI.

Category:

- ``password_extra``: a mutating/login surface exists and ``argon2-cffi`` is not
  installed (``_has_argon2()`` is ``False``). Severity is env-aware: ``WARNING``
  in production/staging, **silent in development** (the default) so dev apps and
  shipped examples — and the scrypt-only base CI env — stay clean. This is a
  posture *advisory*, never an ERROR: scrypt verifies and stores fine, so there
  is no correctness gap to fail loud on. Existing scrypt hashes re-derive to
  argon2 on the next successful login when the app calls
  ``verify_and_upgrade(..., upgrade_algorithm=True)`` (opt-in; storm-safe
  default is off) and persists the returned hash once the extra is installed.

Why **built-in** and not a plugin check: this rule must read ``config.env`` and
the route surface (``router`` + discovered filesystem pages), which the plugin
``ContractCheckSnapshot`` does not expose. It mirrors ``rules_security_stack`` /
``rules_cookie_secure`` in that respect.

argon2 availability is detected via :func:`chirp.security.passwords._has_argon2`
— the *same* predicate the runtime uses to choose the hashing algorithm — not by
sniffing a middleware class name. The "do we hash with argon2 or scrypt?"
decision lives in one place, so the check and the runtime never disagree.
"""

from typing import TYPE_CHECKING, Any

from chirp.contracts.rules_security_stack import is_mutating_route
from chirp.contracts.types import ContractIssue, Severity

if TYPE_CHECKING:
    from chirp.routing.router import Router


def check_password_extra(
    router: Router,
    config: Any,
    discovered_routes: list[Any] | None = None,
) -> list[ContractIssue]:
    """Advise installing ``chirp[auth]`` (argon2) on a production login surface.

    Fires a single ``WARNING`` (production/staging, silent in development) when
    the app has a mutating/login surface and ``argon2-cffi`` is not importable,
    so the password path falls back to scrypt. No issue is emitted for an app
    with no mutating routes, when argon2 is available, or in development.

    ``discovered_routes`` carries the filesystem ``PageRoute`` objects (which
    expose ``actions``); runtime ``router.routes`` expose ``methods`` only. Both
    are scanned so a GET-only page backed by ``_actions.py`` form actions still
    counts as a mutating surface — the same ``is_mutating_route`` definition
    ``security_stack`` owns.
    """
    from chirp.security.passwords import _has_argon2

    if _has_argon2():
        return []

    env = getattr(config, "env", "development")
    if env not in ("production", "staging"):
        return []

    candidate_routes = list(getattr(router, "routes", []))
    if discovered_routes:
        candidate_routes.extend(discovered_routes)
    if not any(is_mutating_route(route) for route in candidate_routes):
        return []

    return [
        ContractIssue(
            severity=Severity.WARNING,
            category="password_extra",
            message=(
                f"App has a login/mutating surface but argon2-cffi is not "
                f"installed (env='{env}'), so password hashing falls back to "
                "stdlib scrypt. argon2id is the recommended production algorithm "
                "— install it with: pip install chirp[auth]. Once installed, "
                "existing scrypt hashes re-derive to argon2 on the next "
                "successful login when you call "
                "verify_and_upgrade(..., upgrade_algorithm=True) and persist "
                "the returned hash."
            ),
        )
    ]
