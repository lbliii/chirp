"""Password hashing utilities — argon2id with scrypt fallback.

Hashes passwords using the best available algorithm:

1. **argon2id** via ``argon2-cffi`` (preferred, ``pip install chirp[auth]``)
2. **scrypt** via stdlib ``hashlib`` (fallback, always available)

Both produce PHC-format strings. ``verify_password`` auto-detects the
algorithm from the hash prefix, so hashes are forward-compatible if
the default changes.

Usage::

    from chirp.security.passwords import hash_password, verify_password

    hashed = hash_password("my-password")
    ok = verify_password("my-password", hashed)
"""

import base64
import hashlib
import hmac
import os

# PHC format prefixes
_ARGON2_PREFIX = "$argon2"
_SCRYPT_PREFIX = "$scrypt$"

# Scrypt parameters (balanced for security and compatibility)
_SCRYPT_N = 2**14  # CPU/memory cost
_SCRYPT_R = 8  # Block size
_SCRYPT_P = 1  # Parallelism
_SCRYPT_DKLEN = 64  # Derived key length
_SALT_LENGTH = 16  # Salt length in bytes


def _has_argon2() -> bool:
    """Check if argon2-cffi is available."""
    try:
        import argon2  # noqa: F401

        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Scrypt (stdlib fallback)
# ---------------------------------------------------------------------------


def _hash_scrypt(password: str) -> str:
    """Hash password with scrypt, returning a PHC-format string."""
    salt = os.urandom(_SALT_LENGTH)
    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    salt_b64 = base64.b64encode(salt).decode("ascii")
    dk_b64 = base64.b64encode(dk).decode("ascii")
    return f"$scrypt$n={_SCRYPT_N},r={_SCRYPT_R},p={_SCRYPT_P}${salt_b64}${dk_b64}"


def _verify_scrypt(password: str, phc_hash: str) -> bool:
    """Verify password against a scrypt PHC-format hash."""
    # Format: $scrypt$n=N,r=R,p=P$salt_b64$dk_b64
    parts = phc_hash.split("$")
    # parts: ['', 'scrypt', 'n=...,r=...,p=...', 'salt_b64', 'dk_b64']
    if len(parts) != 5 or parts[1] != "scrypt":
        return False

    try:
        params = {}
        for param in parts[2].split(","):
            key, _, value = param.partition("=")
            params[key] = int(value)

        salt = base64.b64decode(parts[3])
        expected_dk = base64.b64decode(parts[4])
    except Exception:
        return False

    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=params.get("n", _SCRYPT_N),
        r=params.get("r", _SCRYPT_R),
        p=params.get("p", _SCRYPT_P),
        dklen=len(expected_dk),
    )

    return hmac.compare_digest(dk, expected_dk)


# ---------------------------------------------------------------------------
# Argon2 (preferred)
# ---------------------------------------------------------------------------


def _hash_argon2(password: str) -> str:
    """Hash password with argon2id via argon2-cffi."""
    from argon2 import PasswordHasher

    ph = PasswordHasher()
    return ph.hash(password)


def _verify_argon2(password: str, phc_hash: str) -> bool:
    """Verify password against an argon2 hash."""
    from argon2 import PasswordHasher
    from argon2.exceptions import VerificationError

    ph = PasswordHasher()
    try:
        return ph.verify(phc_hash, password)
    except VerificationError:
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Hash a password using the best available algorithm.

    Uses argon2id if ``argon2-cffi`` is installed (``pip install chirp[auth]``),
    otherwise falls back to scrypt (stdlib).

    Returns a PHC-format string safe for database storage.

    Args:
        password: The plaintext password to hash.

    Returns:
        A PHC-format hash string (e.g. ``$argon2id$...`` or ``$scrypt$...``).
    """
    if not password:
        msg = "Password must not be empty."
        raise ValueError(msg)

    if _has_argon2():
        return _hash_argon2(password)
    return _hash_scrypt(password)


def verify_password(password: str, phc_hash: str) -> bool:
    """Verify a password against a PHC-format hash.

    Auto-detects the algorithm from the hash prefix. This means
    hashes created with argon2 can be verified even if the default
    algorithm later changes (and vice versa).

    Args:
        password: The plaintext password to check.
        phc_hash: The stored hash (from ``hash_password``).

    Returns:
        ``True`` if the password matches, ``False`` otherwise.
    """
    if not password or not phc_hash:
        return False

    if phc_hash.startswith(_ARGON2_PREFIX):
        if not _has_argon2():
            msg = (
                "Hash was created with argon2 but argon2-cffi is not installed. "
                "Install it with: pip install chirp[auth]"
            )
            raise RuntimeError(msg)
        return _verify_argon2(password, phc_hash)

    if phc_hash.startswith(_SCRYPT_PREFIX):
        return _verify_scrypt(password, phc_hash)

    msg = f"Unknown hash format: {phc_hash[:20]}..."
    raise ValueError(msg)
