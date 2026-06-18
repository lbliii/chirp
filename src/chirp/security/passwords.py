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
import logging
import os

# PHC format prefixes
_ARGON2_PREFIX = "$argon2"
_SCRYPT_PREFIX = "$scrypt$"

# Scrypt parameters — N=2^16 exceeds OWASP minimum (2^14) for 2026
_SCRYPT_N = 2**16  # CPU/memory cost
_SCRYPT_R = 8  # Block size
_SCRYPT_P = 1  # Parallelism
_SCRYPT_DKLEN = 64  # Derived key length
_SALT_LENGTH = 16  # Salt length in bytes
_SCRYPT_MAXMEM = 2 * 128 * _SCRYPT_N * _SCRYPT_R  # OpenSSL needs ~2x theoretical

# Argon2id parameters — RFC 9106 §4 second recommended option (memory-constrained:
# t=3, m=2^16 KiB = 64 MiB, p=4). These values intentionally equal argon2-cffi's
# current ``PasswordHasher()`` defaults so existing argon2 hashes keep verifying and
# are not flagged stale by ``check_needs_rehash``. They are stated explicitly (rather
# than relying on library defaults) so the cost factors are auditable and pinned.
_ARGON2_TIME_COST = 3  # iterations
_ARGON2_MEMORY_COST = 65536  # KiB (64 MiB)
_ARGON2_PARALLELISM = 4  # lanes / threads
_ARGON2_HASH_LEN = 32  # output length in bytes
_ARGON2_SALT_LEN = 16  # salt length in bytes


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
        maxmem=_SCRYPT_MAXMEM,
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

        # Fail-closed: hashlib.scrypt rejects malformed cost/length inputs
        # (e.g. a zero-length dk segment → dklen=0) with ValueError. Derive
        # inside the guard so a corrupt hash returns False rather than raising.
        n = params.get("n", _SCRYPT_N)
        r = params.get("r", _SCRYPT_R)
        maxmem = 2 * 128 * n * r
        dk = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=params.get("p", _SCRYPT_P),
            maxmem=maxmem,
            dklen=len(expected_dk),
        )
    except Exception:
        logging.getLogger("chirp.security").debug(
            "Password hash parsing failed (malformed hash string)",
            exc_info=True,
        )
        return False

    return hmac.compare_digest(dk, expected_dk)


# ---------------------------------------------------------------------------
# Argon2 (preferred)
# ---------------------------------------------------------------------------


def _argon2_hasher():
    """Build a ``PasswordHasher`` with explicit, pinned argon2id cost params.

    Cost factors follow RFC 9106 §4 (second recommended option) and are pinned
    to argon2-cffi's current ``PasswordHasher()`` defaults so existing hashes
    still verify. The same construction is used for hashing and verifying so the
    two paths always agree.
    """
    from argon2 import PasswordHasher

    return PasswordHasher(
        time_cost=_ARGON2_TIME_COST,
        memory_cost=_ARGON2_MEMORY_COST,
        parallelism=_ARGON2_PARALLELISM,
        hash_len=_ARGON2_HASH_LEN,
        salt_len=_ARGON2_SALT_LEN,
    )


def _hash_argon2(password: str) -> str:
    """Hash password with argon2id via argon2-cffi."""
    return _argon2_hasher().hash(password)


def _verify_argon2(password: str, phc_hash: str) -> bool:
    """Verify password against an argon2 hash.

    Fails closed: any argon2-cffi failure — a wrong password
    (``VerificationError``, an ``Argon2Error`` subclass) or a malformed/corrupt
    hash string (``InvalidHashError``, which derives from ``ValueError`` — NOT
    from ``Argon2Error``) — returns ``False`` instead of propagating. Both are
    caught so any malformed-input failure fails closed, mirroring the scrypt
    path which returns ``False`` for unparseable hashes.
    """
    from argon2.exceptions import Argon2Error, InvalidHashError

    try:
        return _argon2_hasher().verify(phc_hash, password)
    except Argon2Error, InvalidHashError:
        logging.getLogger("chirp.security").debug(
            "Password hash verification failed (wrong password or malformed hash)",
            exc_info=True,
        )
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
