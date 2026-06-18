"""Security utilities — route protection and password hashing.

Route protection decorators::

    from chirp.security import login_required, requires

    @app.route("/dashboard")
    @login_required
    def dashboard():
        ...

    @app.route("/admin")
    @requires("admin")
    def admin_panel():
        ...

Password hashing (``pip install chirp[auth]``)::

    from chirp.security import hash_password, verify_password

    hashed = hash_password("my-password")
    ok = verify_password("my-password", hashed)

Login verification with a user-enumeration timing defence, plus
opportunistic hash upgrades::

    from chirp.security import verify_login, verify_and_upgrade

    # Unknown user (hash is None) still runs a decoy verify → constant-ish time.
    if not verify_login(password, user.password_hash if user else None):
        return reject()

    # Re-derive stale hashes on a successful login (never on a wrong password).
    ok, new_hash = verify_and_upgrade(password, user.password_hash)
    if new_hash is not None:
        user.password_hash = new_hash

Group -> permission rollup for the flat ``user.permissions`` gate::

    from chirp.security import resolve_permissions

    # Inside your own load_user — most-permissive-wins union over the user's
    # groups, dotted-key flatten, result lands on user.permissions.
    perms = resolve_permissions(
        [group.permissions for group in record.groups],
        base=frozenset(record.direct_permissions),
    )
"""

from chirp.security.audit import SecurityEvent, emit_security_event, set_security_event_sink
from chirp.security.decorators import login_required, requires
from chirp.security.lockout import LockoutConfig, LoginLockout
from chirp.security.passwords import (
    hash_password,
    needs_rehash,
    verify_and_upgrade,
    verify_login,
    verify_password,
)
from chirp.security.resolve_permissions import resolve_permissions

__all__ = [
    "LockoutConfig",
    "LoginLockout",
    "SecurityEvent",
    "emit_security_event",
    "hash_password",
    "login_required",
    "needs_rehash",
    "requires",
    "resolve_permissions",
    "set_security_event_sink",
    "verify_and_upgrade",
    "verify_login",
    "verify_password",
]
