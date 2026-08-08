"""Quota-aware production worker resolution.

``AppConfig.workers=0`` means auto-detect. Pounce resolves that via
``os.cpu_count()``, which reports the *host* CPU count inside containers and
can spawn dozens of workers on a one-vCPU Railway service.

Chirp owns resolution on the production launch path: when ``workers=0``, we
resolve to a concrete count using portable cgroup/cpuset signals (and optional
``WEB_CONCURRENCY``) *before* constructing Pounce ``ServerConfig``. Explicit
``workers=N`` remains authoritative and is passed through unchanged.
"""

from __future__ import annotations

import math
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

_CGROUP_V2_MAX = Path("/sys/fs/cgroup/cpu.max")
_CGROUP_V2_CPUSET_EFFECTIVE = Path("/sys/fs/cgroup/cpuset.cpus.effective")
_CGROUP_V2_CPUSET = Path("/sys/fs/cgroup/cpuset.cpus")
_CGROUP_V1_QUOTA = Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
_CGROUP_V1_PERIOD = Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
_CGROUP_V1_CPUSET = Path("/sys/fs/cgroup/cpuset/cpuset.cpus")


@dataclass(frozen=True, slots=True)
class WorkerResolution:
    """Inputs and outcome for production worker auto-detect."""

    requested: int
    resolved: int
    source: str
    host_cpus: int
    quota_cpus: int | None
    cpuset_cpus: int | None
    platform_concurrency: int | None

    def diagnostic_line(self) -> str:
        """Human-readable startup line naming resolution inputs."""
        parts = [
            f"requested={self.requested}",
            f"host_cpus={self.host_cpus}",
        ]
        if self.quota_cpus is not None:
            parts.append(f"cgroup_quota_cpus={self.quota_cpus}")
        if self.cpuset_cpus is not None:
            parts.append(f"cpuset_cpus={self.cpuset_cpus}")
        if self.platform_concurrency is not None:
            parts.append(f"WEB_CONCURRENCY={self.platform_concurrency}")
        parts.append(f"source={self.source}")
        parts.append(f"resolved={self.resolved}")
        return "chirp workers: " + " ".join(parts)


def parse_cpu_set(spec: str) -> int | None:
    """Count CPUs listed in a Linux cpuset range string (e.g. ``0-3,8``).

    Returns ``None`` for empty/malformed input.
    """
    text = spec.strip()
    if not text or text == "\n":
        return None
    total = 0
    for part in text.split(","):
        token = part.strip()
        if not token:
            return None
        if "-" in token:
            bounds = token.split("-", 1)
            if len(bounds) != 2:
                return None
            try:
                start = int(bounds[0])
                end = int(bounds[1])
            except ValueError:
                return None
            if end < start or start < 0:
                return None
            total += end - start + 1
        else:
            try:
                cpu = int(token)
            except ValueError:
                return None
            if cpu < 0:
                return None
            total += 1
    return total if total > 0 else None


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _cpus_from_quota_ratio(quota: int, period: int) -> int | None:
    """Convert cgroup quota/period into a whole CPU count.

    Uses ceiling division so a fractional allocation (e.g. 0.5 CPU) still yields
    at least one worker. Unlimited quotas (``quota < 0``) return ``None``.
    """
    if period <= 0:
        return None
    if quota < 0:
        return None
    if quota == 0:
        return 1
    return max(1, math.ceil(quota / period))


def read_cgroup_cpu_quota(
    *,
    v2_max: Path | None = None,
    v1_quota: Path | None = None,
    v1_period: Path | None = None,
) -> int | None:
    """Return effective CPU quota as a whole-CPU count, or ``None`` if unknown."""
    max_path = _CGROUP_V2_MAX if v2_max is None else v2_max
    quota_path = _CGROUP_V1_QUOTA if v1_quota is None else v1_quota
    period_path = _CGROUP_V1_PERIOD if v1_period is None else v1_period

    raw = _read_text(max_path)
    if raw is not None:
        parts = raw.strip().split()
        if len(parts) >= 1 and parts[0] == "max":
            return None
        if len(parts) >= 2:
            try:
                quota = int(parts[0])
                period = int(parts[1])
            except ValueError:
                return None
            return _cpus_from_quota_ratio(quota, period)
        return None

    quota_raw = _read_text(quota_path)
    period_raw = _read_text(period_path)
    if quota_raw is None or period_raw is None:
        return None
    try:
        quota = int(quota_raw.strip())
        period = int(period_raw.strip())
    except ValueError:
        return None
    return _cpus_from_quota_ratio(quota, period)


def read_cpuset_cpus(
    *,
    paths: tuple[Path, ...] | None = None,
) -> int | None:
    """Return cpuset size from the first readable cgroup cpuset file."""
    search = (
        (
            _CGROUP_V2_CPUSET_EFFECTIVE,
            _CGROUP_V2_CPUSET,
            _CGROUP_V1_CPUSET,
        )
        if paths is None
        else paths
    )
    for path in search:
        raw = _read_text(path)
        if raw is None:
            continue
        count = parse_cpu_set(raw)
        if count is not None:
            return count
    return None


def _platform_concurrency(environ: Mapping[str, str]) -> int | None:
    """Honor ``WEB_CONCURRENCY`` when it is a positive integer."""
    raw = environ.get("WEB_CONCURRENCY")
    if raw is None or raw.strip() == "":
        return None
    try:
        value = int(raw.strip())
    except ValueError:
        return None
    return value if value > 0 else None


def detect_available_cpus(
    *,
    host_cpus: int | None = None,
    quota_cpus: int | None = None,
    cpuset_cpus: int | None = None,
    cgroup_root: Path | None = None,
) -> tuple[int, int | None, int | None]:
    """Return ``(available, quota_cpus, cpuset_cpus)`` for auto-detect.

    ``available`` is ``min(host, quota?, cpuset?)`` with a floor of 1.
    When ``cgroup_root`` is provided (tests), quota/cpuset are read from that
    tree instead of the live ``/sys/fs/cgroup`` paths.
    """
    host = host_cpus if host_cpus is not None else (os.cpu_count() or 1)
    host = max(1, host)

    if cgroup_root is not None:
        quota_cpus = read_cgroup_cpu_quota(
            v2_max=cgroup_root / "cpu.max",
            v1_quota=cgroup_root / "cpu" / "cpu.cfs_quota_us",
            v1_period=cgroup_root / "cpu" / "cpu.cfs_period_us",
        )
        cpuset_cpus = read_cpuset_cpus(
            paths=(
                cgroup_root / "cpuset.cpus.effective",
                cgroup_root / "cpuset.cpus",
                cgroup_root / "cpuset" / "cpuset.cpus",
            )
        )
    else:
        if quota_cpus is None:
            quota_cpus = read_cgroup_cpu_quota()
        if cpuset_cpus is None:
            cpuset_cpus = read_cpuset_cpus()

    available = host
    if quota_cpus is not None:
        available = min(available, quota_cpus)
    if cpuset_cpus is not None:
        available = min(available, cpuset_cpus)
    return max(1, available), quota_cpus, cpuset_cpus


def resolve_production_workers(
    requested: int,
    *,
    environ: Mapping[str, str] | None = None,
    host_cpus: int | None = None,
    cgroup_root: Path | None = None,
) -> WorkerResolution:
    """Resolve the worker count Chirp should pass to Pounce.

    Rules (measured portable contract for #750):

    1. ``requested > 0`` — explicit; never clamped by quota.
    2. ``requested == 0`` and valid ``WEB_CONCURRENCY`` — platform concurrency.
    3. ``requested == 0`` otherwise — ``min(host_cpus, cgroup_quota?, cpuset?)``,
       floor 1. Missing/malformed cgroup files fall back to the host count.
    4. ``requested < 0`` — treated as auto (same as 0) after clamping intent;
       callers should not pass negatives (Pounce rejects them).
    """
    env = os.environ if environ is None else environ
    host = host_cpus if host_cpus is not None else (os.cpu_count() or 1)
    host = max(1, host)
    platform = _platform_concurrency(env)

    if requested > 0:
        available, quota, cpuset = detect_available_cpus(host_cpus=host, cgroup_root=cgroup_root)
        # Still surface detected signals for diagnostics; do not clamp.
        return WorkerResolution(
            requested=requested,
            resolved=requested,
            source="explicit",
            host_cpus=host,
            quota_cpus=quota,
            cpuset_cpus=cpuset,
            platform_concurrency=platform,
        )

    available, quota, cpuset = detect_available_cpus(host_cpus=host, cgroup_root=cgroup_root)

    if platform is not None:
        return WorkerResolution(
            requested=requested,
            resolved=platform,
            source="web_concurrency",
            host_cpus=host,
            quota_cpus=quota,
            cpuset_cpus=cpuset,
            platform_concurrency=platform,
        )

    if quota is not None and available == quota and (cpuset is None or quota <= cpuset):
        source = "cgroup_quota"
    elif cpuset is not None and available == cpuset:
        source = "cpuset"
    else:
        source = "host_cpu"

    return WorkerResolution(
        requested=requested,
        resolved=available,
        source=source,
        host_cpus=host,
        quota_cpus=quota,
        cpuset_cpus=cpuset,
        platform_concurrency=platform,
    )


def emit_worker_resolution(
    resolution: WorkerResolution,
    *,
    stream: TextIO | None = None,
) -> None:
    """Write the worker resolution diagnostic to stderr (startup visibility)."""
    out = sys.stderr if stream is None else stream
    print(resolution.diagnostic_line(), file=out, flush=True)
