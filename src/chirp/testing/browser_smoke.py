"""Opt-in Playwright shell smoke helpers (#234).

These complement ``app.check()`` and :func:`~chirp.testing.route_smoke.assert_route_smoke`
with runtime checks only a real browser can see: console errors, Alpine boot,
and shell controller presence. Playwright is optional — call
:func:`require_playwright` inside fixtures or tests to skip cleanly when it is
not installed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def require_playwright() -> Any:
    """Import Playwright or skip the current test when unavailable."""
    pytest = __import__("pytest")
    return pytest.importorskip("playwright")


def attach_console_capture(page: Any) -> list[str]:
    """Attach console/pageerror collectors to *page* and return the error buffer."""
    errors: list[str] = []

    def _record_console(msg: Any) -> None:
        if msg.type != "error":
            return
        errors.append(f"console.{msg.type}: {msg.text}")

    page.on("console", _record_console)
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    return errors


def filter_console_errors(
    errors: list[str],
    *,
    ignore: Callable[[str], bool] | None = None,
) -> list[str]:
    """Return *errors* minus entries accepted by *ignore*."""
    if ignore is None:
        return list(errors)
    return [entry for entry in errors if not ignore(entry)]


def assert_alpine_booted(page: Any) -> None:
    """Assert ``window.Alpine`` is defined — the shell controllers mounted."""
    ok = page.evaluate("() => typeof window.Alpine !== 'undefined'")
    if not ok:
        raise AssertionError("window.Alpine is undefined — the shell did not initialize")


def assert_zero_console_errors(errors: list[str], *, context: str = "") -> None:
    """Fail when *errors* is non-empty."""
    if errors:
        prefix = f"{context}: " if context else ""
        raise AssertionError(f"{prefix}browser errors: {errors}")
