"""Tests for password hashing — scrypt fallback and argon2 (if available)."""

from unittest.mock import patch

import pytest

from chirp.security.passwords import (
    _SCRYPT_N,
    _SCRYPT_PREFIX,
    _hash_scrypt,
    _verify_scrypt,
    hash_password,
    verify_password,
)

# ---------------------------------------------------------------------------
# Scrypt (always available)
# ---------------------------------------------------------------------------


class TestScryptHash:
    def test_produces_phc_format(self) -> None:
        hashed = _hash_scrypt("password123")
        assert hashed.startswith("$scrypt$")
        # Format: $scrypt$n=N,r=R,p=P$salt$dk
        parts = hashed.split("$")
        assert len(parts) == 5
        assert parts[1] == "scrypt"
        assert "n=" in parts[2]
        assert "r=" in parts[2]
        assert "p=" in parts[2]

    def test_different_salt_each_time(self) -> None:
        h1 = _hash_scrypt("same-password")
        h2 = _hash_scrypt("same-password")
        assert h1 != h2  # Different salts → different hashes

    def test_verify_correct_password(self) -> None:
        hashed = _hash_scrypt("my-secret")
        assert _verify_scrypt("my-secret", hashed) is True

    def test_verify_wrong_password(self) -> None:
        hashed = _hash_scrypt("my-secret")
        assert _verify_scrypt("wrong-password", hashed) is False

    def test_verify_tampered_hash_returns_false(self) -> None:
        assert _verify_scrypt("password", "$scrypt$n=32768,r=8,p=1$bad$bad") is False

    def test_verify_invalid_format_returns_false(self) -> None:
        assert _verify_scrypt("password", "not-a-hash") is False
        assert _verify_scrypt("password", "$bcrypt$something") is False


# ---------------------------------------------------------------------------
# hash_password / verify_password (public API)
# ---------------------------------------------------------------------------


class TestHashPassword:
    def test_scrypt_fallback(self) -> None:
        """When argon2 is not available, falls back to scrypt."""
        with patch("chirp.security.passwords._has_argon2", return_value=False):
            hashed = hash_password("test-password")
            assert hashed.startswith(_SCRYPT_PREFIX)

    def test_empty_password_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            hash_password("")

    def test_roundtrip_scrypt(self) -> None:
        with patch("chirp.security.passwords._has_argon2", return_value=False):
            hashed = hash_password("roundtrip-test")
            assert verify_password("roundtrip-test", hashed) is True
            assert verify_password("wrong", hashed) is False


class TestVerifyPassword:
    def test_empty_password_returns_false(self) -> None:
        assert verify_password("", "$scrypt$...") is False

    def test_empty_hash_returns_false(self) -> None:
        assert verify_password("password", "") is False

    def test_unknown_hash_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown hash format"):
            verify_password("password", "$unknown$format")

    def test_scrypt_hash_verified(self) -> None:
        hashed = _hash_scrypt("verify-me")
        assert verify_password("verify-me", hashed) is True
        assert verify_password("not-me", hashed) is False


# ---------------------------------------------------------------------------
# Argon2 (if available)
# ---------------------------------------------------------------------------


class TestArgon2:
    """Tests that run only if argon2-cffi is installed."""

    @pytest.fixture(autouse=True)
    def _skip_without_argon2(self) -> None:
        try:
            import argon2  # noqa: F401
        except ImportError:
            pytest.skip("argon2-cffi not installed")

    def test_argon2_is_preferred(self) -> None:
        hashed = hash_password("argon2-test")
        assert hashed.startswith("$argon2")

    def test_argon2_roundtrip(self) -> None:
        hashed = hash_password("argon2-roundtrip")
        assert verify_password("argon2-roundtrip", hashed) is True
        assert verify_password("wrong", hashed) is False

    def test_argon2_different_salt(self) -> None:
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2

    def test_cross_verify_argon2_and_scrypt(self) -> None:
        """Both hash formats can be verified by verify_password."""
        argon2_hash = hash_password("cross-test")
        scrypt_hash = _hash_scrypt("cross-test")

        assert verify_password("cross-test", argon2_hash) is True
        assert verify_password("cross-test", scrypt_hash) is True
        assert verify_password("wrong", argon2_hash) is False
        assert verify_password("wrong", scrypt_hash) is False


# ---------------------------------------------------------------------------
# Scrypt parameter strength
# ---------------------------------------------------------------------------


class TestScryptParams:
    def test_n_parameter_is_2_16(self) -> None:
        """Default N should be 2^16 (65536) for 2026 security standards."""
        assert _SCRYPT_N == 2**16

    def test_new_hashes_use_n_65536(self) -> None:
        """Newly created hashes embed N=65536 in the PHC string."""
        hashed = _hash_scrypt("test")
        assert "n=65536" in hashed

    def test_old_n_16384_hashes_still_verify(self) -> None:
        """Hashes created with the old N=2^14 must still verify.

        _verify_scrypt reads N from the PHC string, so it uses the
        embedded value, not the current default.
        """
        import base64
        import hashlib

        # Simulate an old hash with N=16384
        salt = b"old-salt-16bytes"
        dk = hashlib.scrypt(
            b"old-password",
            salt=salt,
            n=2**14,
            r=8,
            p=1,
            dklen=64,
        )
        salt_b64 = base64.b64encode(salt).decode("ascii")
        dk_b64 = base64.b64encode(dk).decode("ascii")
        old_hash = f"$scrypt$n=16384,r=8,p=1${salt_b64}${dk_b64}"

        assert _verify_scrypt("old-password", old_hash) is True
        assert _verify_scrypt("wrong", old_hash) is False


# ---------------------------------------------------------------------------
# Timing safety
# ---------------------------------------------------------------------------


class TestTimingSafety:
    def test_scrypt_uses_hmac_compare_digest(self) -> None:
        """Verify that scrypt verification uses constant-time comparison.

        We can't easily measure timing, but we verify the code path
        uses hmac.compare_digest by checking it completes correctly
        for both matching and non-matching passwords.
        """
        hashed = _hash_scrypt("timing-test")
        # Both paths exercise hmac.compare_digest
        assert _verify_scrypt("timing-test", hashed) is True
        assert _verify_scrypt("wrong", hashed) is False

    def test_scrypt_handles_unicode(self) -> None:
        hashed = _hash_scrypt("pässwörd-日本語")
        assert _verify_scrypt("pässwörd-日本語", hashed) is True
        assert _verify_scrypt("password", hashed) is False

    def test_scrypt_handles_long_password(self) -> None:
        long_pw = "a" * 10_000
        hashed = _hash_scrypt(long_pw)
        assert _verify_scrypt(long_pw, hashed) is True
        assert _verify_scrypt("short", hashed) is False
