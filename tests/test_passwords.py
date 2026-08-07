"""Tests for password hashing — scrypt fallback and argon2 (if available)."""

from unittest.mock import patch

import pytest

from chirp.security.passwords import (
    _ARGON2_HASH_LEN,
    _ARGON2_MEMORY_COST,
    _ARGON2_PARALLELISM,
    _ARGON2_SALT_LEN,
    _ARGON2_TIME_COST,
    _SCRYPT_N,
    _SCRYPT_PREFIX,
    _SCRYPT_R,
    _has_argon2,
    _hash_argon2,
    _hash_scrypt,
    _verify_argon2,
    _verify_scrypt,
    hash_password,
    needs_rehash,
    verify_and_upgrade,
    verify_login,
    verify_password,
)


def _scrypt_hash_with(n: int, r: int = _SCRYPT_R, p: int = 1) -> str:
    """Build a scrypt PHC hash for ``test`` with explicit n/r/p cost factors."""
    import base64
    import hashlib

    salt = b"sixteen-byteslt!"
    dk = hashlib.scrypt(b"test", salt=salt, n=n, r=r, p=p, maxmem=2 * 128 * n * r, dklen=64)
    salt_b64 = base64.b64encode(salt).decode("ascii")
    dk_b64 = base64.b64encode(dk).decode("ascii")
    return f"$scrypt$n={n},r={r},p={p}${salt_b64}${dk_b64}"


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

    def test_verify_corrupt_hash_fails_closed(self) -> None:
        """Fail-closed contract: a corrupt/truncated scrypt hash returns False,

        never raises. This is the default-env mirror of the argon2 fail-closed
        guard (argon2-cffi is optional and often absent), so the contract is
        covered even when the auth extra is not installed.
        """
        # Truncated PHC string (missing dk segment).
        assert _verify_scrypt("password", "$scrypt$n=65536,r=8,p=1$c2FsdA==") is False
        # Non-base64 salt/dk segments.
        assert _verify_scrypt("password", "$scrypt$n=65536,r=8,p=1$!!!$!!!") is False
        # Garbage params.
        assert _verify_scrypt("password", "$scrypt$n=abc,r=8,p=1$c2FsdA==$ZGs=") is False


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
# Argon2 fail-closed + cost params (if available)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _has_argon2(), reason="argon2-cffi not installed")
class TestArgon2FailClosed:
    """Argon2 hardening — fail-closed verification and pinned cost params.

    Guarded with skipif (not a fixture) so the base env, which has no
    argon2-cffi, skips cleanly instead of erroring on import.
    """

    def test_verify_corrupt_hash_fails_closed(self) -> None:
        """A corrupt/truncated argon2 hash returns False, never raises.

        Two distinct argon2-cffi failure families must both fail closed:
        ``VerificationError`` (an ``Argon2Error``) for inputs that parse but do
        not match, and ``InvalidHashError`` (a ``ValueError`` — NOT an
        ``Argon2Error``) for unparseable strings. Catching only ``Argon2Error``
        would let the ``InvalidHashError`` inputs below raise a 500.
        """
        # VerificationError territory (parseable PHC, no match).
        assert _verify_argon2("password", "$argon2id$v=19$m=65536,t=3,p=4$short") is False
        assert _verify_argon2("password", "$argon2id$not-a-valid-hash") is False
        assert _verify_argon2("password", "$argon2id$") is False
        # InvalidHashError territory (unparseable) — these are the inputs that
        # raise ValueError-derived InvalidHashError, the real fail-open gap.
        assert _verify_argon2("password", "$argon2") is False
        assert _verify_argon2("password", "$argon2$garbage") is False

    def test_verify_password_routes_invalid_argon2_closed(self) -> None:
        """The public verify_password() must not 500 on a malformed $argon2 hash.

        verify_password routes anything starting with ``$argon2`` to the argon2
        path; a bare/garbage ``$argon2*`` hash hits InvalidHashError. Proven
        through the public API, which is the actual fail-open surface.
        """
        assert verify_password("password", "$argon2") is False
        assert (
            verify_password(
                "password",
                "$argon2xyz$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA",
            )
            is False
        )

    def test_fresh_hash_verifies_with_documented_params(self) -> None:
        """A freshly created argon2 hash verifies and embeds the pinned costs."""
        hashed = _hash_argon2("argon2-cost-params")

        assert hashed.startswith("$argon2id$")
        # Cost factors are embedded in the PHC string.
        assert f"m={_ARGON2_MEMORY_COST}" in hashed
        assert f"t={_ARGON2_TIME_COST}" in hashed
        assert f"p={_ARGON2_PARALLELISM}" in hashed
        # Round-trips through the same explicit construction.
        assert _verify_argon2("argon2-cost-params", hashed) is True
        assert _verify_argon2("wrong", hashed) is False

    def test_pinned_params_equal_library_defaults(self) -> None:
        """Pinned costs must equal argon2-cffi's PasswordHasher() defaults.

        If they diverge, existing argon2 hashes would be flagged stale by
        check_needs_rehash. This asserts the pin against the live library.
        """
        from argon2 import PasswordHasher

        default = PasswordHasher()
        assert default.time_cost == _ARGON2_TIME_COST
        assert default.memory_cost == _ARGON2_MEMORY_COST
        assert default.parallelism == _ARGON2_PARALLELISM
        assert default.hash_len == _ARGON2_HASH_LEN
        assert default.salt_len == _ARGON2_SALT_LEN


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


# ---------------------------------------------------------------------------
# needs_rehash
# ---------------------------------------------------------------------------


class TestNeedsRehashScrypt:
    """Scrypt-path rehash detection — no argon2 required, covers the base env."""

    def test_below_current_n_is_stale(self) -> None:
        old_hash = _scrypt_hash_with(n=2**14)  # below current 2**16
        assert needs_rehash(old_hash) is True

    def test_at_current_params_not_stale(self) -> None:
        """A scrypt hash at the current n/r is current — when argon2 is absent.

        With argon2 installed it becomes the default algorithm, so the scrypt
        hash is only flagged via the gated upgrade_algorithm clause (asserted
        separately). Here we pin the parameter-staleness contract to the
        no-argon2 world so it holds in the base scrypt-fallback env.
        """
        current_hash = _scrypt_hash_with(n=_SCRYPT_N, r=_SCRYPT_R)
        with patch("chirp.security.passwords._has_argon2", return_value=False):
            assert needs_rehash(current_hash) is False

    def test_below_current_r_is_stale(self) -> None:
        old_hash = _scrypt_hash_with(n=_SCRYPT_N, r=_SCRYPT_R - 1)
        assert needs_rehash(old_hash) is True

    def test_empty_hash_is_stale(self) -> None:
        assert needs_rehash("") is True

    def test_unknown_format_is_stale(self) -> None:
        assert needs_rehash("$bcrypt$whatever") is True

    def test_malformed_scrypt_is_stale(self) -> None:
        assert needs_rehash("$scrypt$n=abc,r=8,p=1$x$y") is True


class TestNeedsRehashUpgradeGating:
    """The algorithm-upgrade clause is gated behind upgrade_algorithm."""

    def test_default_off_does_not_flag_current_scrypt_when_argon2_available(self) -> None:
        """Default (upgrade_algorithm=False): a current scrypt hash is NOT stale
        merely because argon2 is now available — avoids a fleet-wide rehash storm.
        """
        current_hash = _scrypt_hash_with(n=_SCRYPT_N, r=_SCRYPT_R)
        with patch("chirp.security.passwords._has_argon2", return_value=True):
            assert needs_rehash(current_hash, upgrade_algorithm=False) is False

    def test_opt_in_flags_scrypt_when_argon2_available(self) -> None:
        current_hash = _scrypt_hash_with(n=_SCRYPT_N, r=_SCRYPT_R)
        with patch("chirp.security.passwords._has_argon2", return_value=True):
            assert needs_rehash(current_hash, upgrade_algorithm=True) is True

    def test_opt_in_no_op_when_argon2_absent(self) -> None:
        """upgrade_algorithm=True with no argon2 falls back to param staleness."""
        current_hash = _scrypt_hash_with(n=_SCRYPT_N, r=_SCRYPT_R)
        with patch("chirp.security.passwords._has_argon2", return_value=False):
            assert needs_rehash(current_hash, upgrade_algorithm=True) is False


@pytest.mark.skipif(not _has_argon2(), reason="argon2-cffi not installed")
class TestNeedsRehashArgon2:
    """Argon2-path rehash detection — only when argon2-cffi is installed."""

    def test_fresh_argon2_not_stale(self) -> None:
        fresh = _hash_argon2("argon2-fresh")
        assert needs_rehash(fresh) is False

    def test_weak_argon2_is_stale(self) -> None:
        """A real argon2 hash below the pinned cost is flagged by check_needs_rehash."""
        from argon2 import PasswordHasher

        weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash("weak")
        assert needs_rehash(weak) is True

    def test_corrupt_argon2_is_stale(self) -> None:
        assert needs_rehash("$argon2id$garbage") is True


# ---------------------------------------------------------------------------
# verify_and_upgrade
# ---------------------------------------------------------------------------


class TestVerifyAndUpgrade:
    def test_correct_and_stale_returns_new_hash(self) -> None:
        old_hash = _scrypt_hash_with(n=2**14)  # stale (below current n)
        ok, new_hash = verify_and_upgrade("test", old_hash)
        assert ok is True
        assert new_hash is not None
        assert new_hash != old_hash
        assert verify_password("test", new_hash) is True

    def test_correct_and_current_returns_none(self) -> None:
        with patch("chirp.security.passwords._has_argon2", return_value=False):
            current_hash = hash_password("current-pw")  # scrypt at current params
            ok, new_hash = verify_and_upgrade("current-pw", current_hash)
            assert ok is True
            assert new_hash is None

    def test_wrong_password_returns_false_none_and_never_rehashes(self) -> None:
        old_hash = _scrypt_hash_with(n=2**14)  # stale, but the guess is wrong
        with patch("chirp.security.passwords.hash_password") as spy_hash:
            ok, new_hash = verify_and_upgrade("wrong-guess", old_hash)
        assert ok is False
        assert new_hash is None
        # A wrong password must NEVER trigger a rehash (no DB write on bad guess).
        spy_hash.assert_not_called()

    @pytest.mark.issue(751)
    def test_default_does_not_upgrade_current_scrypt_when_argon2_available(
        self,
    ) -> None:
        """Storm-safe default: current-cost scrypt is not replaced solely
        because argon2 became available (#751).
        """
        current_hash = _scrypt_hash_with(n=_SCRYPT_N, r=_SCRYPT_R)
        with (
            patch("chirp.security.passwords._has_argon2", return_value=True),
            patch("chirp.security.passwords.hash_password") as spy_hash,
        ):
            ok, new_hash = verify_and_upgrade("test", current_hash)
        assert ok is True
        assert new_hash is None
        spy_hash.assert_not_called()

    @pytest.mark.issue(751)
    def test_opt_in_no_op_when_argon2_absent(self) -> None:
        """upgrade_algorithm=True without argon2 stays on param staleness (#751)."""
        current_hash = _scrypt_hash_with(n=_SCRYPT_N, r=_SCRYPT_R)
        with patch("chirp.security.passwords._has_argon2", return_value=False):
            ok, new_hash = verify_and_upgrade("test", current_hash, upgrade_algorithm=True)
        assert ok is True
        assert new_hash is None

    @pytest.mark.issue(751)
    def test_wrong_password_never_upgrades_even_with_opt_in(self) -> None:
        current_hash = _scrypt_hash_with(n=_SCRYPT_N, r=_SCRYPT_R)
        with (
            patch("chirp.security.passwords._has_argon2", return_value=True),
            patch("chirp.security.passwords.hash_password") as spy_hash,
        ):
            ok, new_hash = verify_and_upgrade("wrong-guess", current_hash, upgrade_algorithm=True)
        assert ok is False
        assert new_hash is None
        spy_hash.assert_not_called()


@pytest.mark.skipif(not _has_argon2(), reason="argon2-cffi not installed")
class TestVerifyAndUpgradeArgon2:
    def test_correct_and_current_argon2_returns_none(self) -> None:
        current = _hash_argon2("argon2-current")
        ok, new_hash = verify_and_upgrade("argon2-current", current)
        assert ok is True
        assert new_hash is None

    @pytest.mark.issue(751)
    def test_opt_in_upgrades_current_scrypt_to_argon2(self) -> None:
        """upgrade_algorithm=True rehashes current-cost scrypt → argon2id (#751)."""
        current_hash = _scrypt_hash_with(n=_SCRYPT_N, r=_SCRYPT_R)
        ok, new_hash = verify_and_upgrade("test", current_hash, upgrade_algorithm=True)
        assert ok is True
        assert new_hash is not None
        assert new_hash.startswith("$argon2id$")
        # Persistence step apps must perform — replacement verifies after store.
        assert verify_password("test", new_hash) is True


# ---------------------------------------------------------------------------
# verify_login (user-enumeration timing defence)
# ---------------------------------------------------------------------------


class TestVerifyLogin:
    def test_unknown_user_returns_false(self) -> None:
        assert verify_login("any-password", None) is False

    def test_unknown_user_invokes_decoy_path(self) -> None:
        """phc_hash=None must still run a verify against the decoy hash.

        Spy on the decoy accessor + verify_password rather than timing the
        wall clock (flaky). The decoy must be consulted and verified so the
        unknown-user path burns comparable work to a wrong-password path.
        """
        with (
            patch("chirp.security.passwords._decoy_hash", return_value="$decoy$") as spy_decoy,
            patch("chirp.security.passwords.verify_password", return_value=False) as spy_verify,
        ):
            assert verify_login("attacker-guess", None) is False
        spy_decoy.assert_called_once()
        spy_verify.assert_called_once_with("attacker-guess", "$decoy$")

    def test_known_user_matching_password(self) -> None:
        hashed = _hash_scrypt("real-password")
        assert verify_login("real-password", hashed) is True

    def test_known_user_wrong_password(self) -> None:
        hashed = _hash_scrypt("real-password")
        assert verify_login("wrong-password", hashed) is False

    def test_known_user_path_does_not_touch_decoy(self) -> None:
        hashed = _hash_scrypt("real-password")
        with patch("chirp.security.passwords._decoy_hash") as spy_decoy:
            assert verify_login("real-password", hashed) is True
        spy_decoy.assert_not_called()

    def test_behaves_like_verify_password_for_known_user(self) -> None:
        hashed = _hash_scrypt("parity-check")
        assert verify_login("parity-check", hashed) == verify_password("parity-check", hashed)
        assert verify_login("nope", hashed) == verify_password("nope", hashed)


class TestDecoyThreadSafety:
    def test_decoy_computed_once_under_concurrency(self) -> None:
        """Concurrent first-touch must compute the decoy exactly once.

        A naive ``if _DECOY_HASH is None`` races: N threads each hash the decoy
        on the first concurrent burst. The threading.Lock around the lazy init
        must collapse that to a single hash_password call.
        """
        import threading

        import chirp.security.passwords as pw

        # Reset module state so this test owns the once-only init.
        with pw._DECOY_LOCK:
            pw._DECOY_HASH = None

        call_count = 0
        real_hash = pw.hash_password

        def counting_hash(password: str) -> str:
            nonlocal call_count
            call_count += 1
            return real_hash(password)

        results: list[str] = []
        barrier = threading.Barrier(8)

        def worker() -> None:
            barrier.wait()  # maximize contention on the first touch
            results.append(pw._decoy_hash())

        with patch.object(pw, "hash_password", counting_hash):
            threads = [threading.Thread(target=worker) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert call_count == 1, f"decoy hashed {call_count} times, expected exactly 1"
        assert len(set(results)) == 1  # every thread saw the same published hash
