"""In-memory user store — the demo account behind Lucky Cat's auth.

Lucky Cat is **public-browse, gated-trading**: the markets grid and a market's
detail page are open to anyone, but the account surfaces (trade, portfolio,
watchlist, activity, settings) and every mutation (deposit, place/cancel order,
convert, toggle a star, mark notifications read) require a signed-in user.

This is a **single shared demo account**, deliberately — the same doctrine that
pins ``workers=1`` (see DESIGN.md §7): the wallet, trade store, watchlist and
notifications all live in one process's memory, so there is one account everyone
signs in to. Real per-user state needs an external store + a shared bus
backplane, which is the production scaling path (out of scope for the demo).

The store follows the example's store convention exactly (see ``wallet.py`` /
``trade_store.py``): a **frozen** model, module-level state behind a single
``threading.Lock``, immutable reads out, and a ``reset()`` for test isolation
(wired into ``conftest.py``).

Passwords are hashed with :mod:`chirp.security.passwords` — argon2id when
``chirp[auth]`` (``argon2-cffi``) is installed, else the stdlib **scrypt**
fallback (always available, no extra dependency). ``verify_password``
auto-detects the algorithm from the PHC prefix, so the demo runs on the slim
deploy image (which drops ``argon2-cffi``) with no code change.
"""

import threading
from dataclasses import dataclass

from chirp.security.passwords import hash_password, verify_password

# ---------------------------------------------------------------------------
# Demo credentials — shown on the login page so the live demo is frictionless
# (prefilled + hinted). Demo only; never a real secret.
# ---------------------------------------------------------------------------

DEMO_USERNAME = "neko"
DEMO_PASSWORD = "luckycat"  # demo-only credential, shown on the login page
DEMO_NAME = "Demo Trader"
DEMO_HANDLE = "@neko"


@dataclass(frozen=True, slots=True)
class User:
    """The demo user — satisfies chirp's ``User`` / ``UserWithPermissions``.

    ``id`` + ``is_authenticated`` satisfy the ``User`` protocol that
    ``AuthMiddleware`` / ``@login_required`` read; ``permissions`` additionally
    satisfies ``UserWithPermissions`` so the same model is ready for
    ``@requires("trader")`` permission gating without a remodel.
    """

    id: str
    name: str
    handle: str
    password_hash: str
    permissions: frozenset[str] = frozenset()
    is_authenticated: bool = True


# Hash the demo password ONCE at import (scrypt at OWASP-2026 cost is tens of ms);
# reset() reuses this constant so per-test reseeding stays cheap.
_DEMO_PASSWORD_HASH = hash_password(DEMO_PASSWORD)

_lock = threading.Lock()
_users: dict[str, User] = {}


def _seed() -> dict[str, User]:
    """The seed account set — one demo trader with the ``trader`` permission."""
    return {
        DEMO_USERNAME: User(
            id=DEMO_USERNAME,
            name=DEMO_NAME,
            handle=DEMO_HANDLE,
            password_hash=_DEMO_PASSWORD_HASH,
            permissions=frozenset({"trader"}),
        ),
    }


def reset() -> None:
    """Restore the seed accounts (test isolation; wired into conftest.py)."""
    global _users
    with _lock:
        _users = _seed()


# Seed at import so the store is populated for the first request / app.check().
reset()


def get(user_id: str) -> User | None:
    """Load a user by id — the ``AuthConfig.load_user`` callback (per request)."""
    with _lock:
        return _users.get(user_id)


def authenticate(username: str, password: str) -> User | None:
    """Return the user iff the password verifies, else ``None``.

    The single credential-check path: a blank/unknown username or a wrong
    password is an indistinguishable ``None`` (no user-enumeration signal).
    """
    user = get((username or "").strip())
    if user is not None and verify_password(password or "", user.password_hash):
        return user
    return None
