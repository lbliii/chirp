"""Tests for login lockout primitives."""

from chirp.security.lockout import LockoutConfig, LoginLockout


def test_lockout_after_max_failures() -> None:
    lockout = LoginLockout(LockoutConfig(max_failures=2, window_seconds=60, base_lock_seconds=30))
    locked1, _ = lockout.record_failure("alice")
    locked2, retry = lockout.record_failure("alice")
    assert locked1 is False
    assert locked2 is True
    assert retry > 0


def test_lockout_clears_on_success() -> None:
    lockout = LoginLockout(LockoutConfig(max_failures=2, window_seconds=60, base_lock_seconds=30))
    lockout.record_failure("alice")
    lockout.record_failure("alice")
    lockout.record_success("alice")
    locked, retry = lockout.is_locked("alice")
    assert locked is False
    assert retry == 0
