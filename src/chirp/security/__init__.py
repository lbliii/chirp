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
"""

from chirp.security.audit import SecurityEvent, emit_security_event, set_security_event_sink
from chirp.security.decorators import login_required, requires
from chirp.security.lockout import LockoutConfig, LoginLockout
from chirp.security.passwords import hash_password, verify_password

__all__ = [
    "LockoutConfig",
    "LoginLockout",
    "SecurityEvent",
    "emit_security_event",
    "hash_password",
    "login_required",
    "requires",
    "set_security_event_sink",
    "verify_password",
]
