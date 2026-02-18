"""Login lockout primitives.

Framework-level helper for tracking repeated authentication failures.
Applications call this from login handlers.
"""

import threading
from dataclasses import dataclass
from time import time


@dataclass(frozen=True, slots=True)
class LockoutConfig:
    """Lockout policy configuration."""

    max_failures: int = 5
    window_seconds: int = 900
    base_lock_seconds: int = 300
    backoff_multiplier: float = 1.0
    max_lock_seconds: int = 3600


class LoginLockout:
    """Track login failures and compute lockout windows."""

    __slots__ = ("_config", "_lock", "_state")

    def __init__(self, config: LockoutConfig | None = None) -> None:
        self._config = config or LockoutConfig()
        self._lock = threading.Lock()
        # key -> (failures, first_failure_at, locked_until)
        self._state: dict[str, tuple[int, float, float]] = {}

    def is_locked(self, key: str) -> tuple[bool, int]:
        """Return lock status and retry-after seconds."""
        now = time()
        with self._lock:
            _failures, _first_failure_at, locked_until = self._state.get(key, (0, now, 0.0))
            if locked_until <= now:
                return False, 0
            return True, max(1, int(locked_until - now))

    def record_success(self, key: str) -> None:
        """Clear failure state after successful authentication."""
        with self._lock:
            self._state.pop(key, None)

    def record_failure(self, key: str) -> tuple[bool, int]:
        """Record a failed attempt and return lock status.

        Returns ``(is_locked, retry_after_seconds)``.
        """
        cfg = self._config
        now = time()
        with self._lock:
            failures, first_failure_at, locked_until = self._state.get(key, (0, now, 0.0))

            if locked_until > now:
                return True, max(1, int(locked_until - now))

            if now - first_failure_at > cfg.window_seconds:
                failures = 0
                first_failure_at = now

            failures += 1
            if failures >= cfg.max_failures:
                backoff_steps = max(0, failures - cfg.max_failures)
                multiplier = cfg.backoff_multiplier**backoff_steps
                lock_seconds = int(cfg.base_lock_seconds * multiplier)
                lock_seconds = min(cfg.max_lock_seconds, max(1, lock_seconds))
                locked_until = now + lock_seconds
                self._state[key] = (failures, first_failure_at, locked_until)
                return True, lock_seconds

            self._state[key] = (failures, first_failure_at, 0.0)
            return False, 0
