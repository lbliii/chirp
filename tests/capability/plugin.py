"""Pytest plugin: fail specialized capability lanes on unexpected skips (#917).

Activated only when ``CHIRP_CAPABILITY_LANE`` is set to a registered lane name.
Ordinary local / default-unit runs leave the env unset and keep soft skips.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from tests.capability.lanes import (
    CAPABILITY_LANE_ENV,
    format_collection_failure,
    format_skip_failure,
    get_lane,
    is_allowed_skip,
    missing_required_selectors,
)

if TYPE_CHECKING:
    from tests.capability.lanes import CapabilityLane


def _active_lane_name() -> str | None:
    raw = os.environ.get(CAPABILITY_LANE_ENV, "").strip()
    return raw or None


def _skip_reason(report: pytest.CollectReport | pytest.TestReport) -> str:
    longrepr = report.longrepr
    if isinstance(longrepr, tuple) and len(longrepr) >= 3:
        return str(longrepr[2]).strip()
    if longrepr is None:
        return "(no skip reason)"
    return str(longrepr).strip()


class _CapabilityLanePlugin:
    """Session-scoped enforcer registered only when a lane env is set."""

    def __init__(self, lane: CapabilityLane) -> None:
        self.lane = lane
        self.unexpected_skips: list[tuple[str, str]] = []

    def _record(self, nodeid: str, reason: str) -> None:
        if is_allowed_skip(self.lane, reason):
            return
        self.unexpected_skips.append((nodeid, reason))

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        nodeids = [item.nodeid for item in session.items]
        missing = missing_required_selectors(self.lane, nodeids)
        if missing:
            pytest.exit(
                format_collection_failure(self.lane, missing),
                returncode=int(pytest.ExitCode.TESTS_FAILED),
            )

    def pytest_collectreport(self, report: pytest.CollectReport) -> None:
        # Module-level importorskip / collection skips.
        if not report.skipped:
            return
        nodeid = report.nodeid or str(getattr(report, "fspath", "")) or "<collection>"
        self._record(str(nodeid), _skip_reason(report))

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if not report.skipped:
            return
        if report.when not in ("setup", "call"):
            return
        self._record(report.nodeid, _skip_reason(report))

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        if not self.unexpected_skips:
            return
        writer = session.config.get_terminal_writer()
        writer.line("")
        writer.sep("!", "capability lane skip-fail (#917)")
        writer.line(format_skip_failure(self.lane, self.unexpected_skips))
        if exitstatus == int(pytest.ExitCode.OK):
            session.exitstatus = int(pytest.ExitCode.TESTS_FAILED)


def pytest_configure(config: pytest.Config) -> None:
    name = _active_lane_name()
    if name is None:
        return
    try:
        lane = get_lane(name)
    except KeyError as exc:
        raise pytest.UsageError(str(exc)) from exc
    config.pluginmanager.register(_CapabilityLanePlugin(lane), name="chirp_capability_lane")
