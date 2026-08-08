"""Quota-aware production worker auto-detect (#750)."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from chirp import App
from chirp.config import AppConfig
from chirp.server.workers import (
    WorkerResolution,
    detect_available_cpus,
    emit_worker_resolution,
    parse_cpu_set,
    read_cgroup_cpu_quota,
    read_cpuset_cpus,
    resolve_production_workers,
)


@pytest.mark.issue(750)
def test_parse_cpu_set_ranges_and_lists() -> None:
    assert parse_cpu_set("0-3") == 4
    assert parse_cpu_set("0-3,8") == 5
    assert parse_cpu_set("2") == 1
    assert parse_cpu_set(" 0-1, 4-5 ") == 4


@pytest.mark.issue(750)
def test_parse_cpu_set_rejects_malformed() -> None:
    assert parse_cpu_set("") is None
    assert parse_cpu_set("abc") is None
    assert parse_cpu_set("3-1") is None
    assert parse_cpu_set("-1") is None
    assert parse_cpu_set("0-") is None


@pytest.mark.issue(750)
def test_cgroup_v2_quota_one_cpu(tmp_path: Path) -> None:
    (tmp_path / "cpu.max").write_text("100000 100000\n", encoding="utf-8")
    assert read_cgroup_cpu_quota(v2_max=tmp_path / "cpu.max") == 1


@pytest.mark.issue(750)
def test_cgroup_v2_quota_fractional_ceils_to_one(tmp_path: Path) -> None:
    (tmp_path / "cpu.max").write_text("50000 100000\n", encoding="utf-8")
    assert read_cgroup_cpu_quota(v2_max=tmp_path / "cpu.max") == 1


@pytest.mark.issue(750)
def test_cgroup_v2_quota_max_is_unlimited(tmp_path: Path) -> None:
    (tmp_path / "cpu.max").write_text("max 100000\n", encoding="utf-8")
    assert read_cgroup_cpu_quota(v2_max=tmp_path / "cpu.max") is None


@pytest.mark.issue(750)
def test_cgroup_v2_malformed_falls_back(tmp_path: Path) -> None:
    (tmp_path / "cpu.max").write_text("not-a-quota\n", encoding="utf-8")
    assert read_cgroup_cpu_quota(v2_max=tmp_path / "cpu.max") is None


@pytest.mark.issue(750)
def test_cgroup_v1_quota(tmp_path: Path) -> None:
    cpu = tmp_path / "cpu"
    cpu.mkdir()
    (cpu / "cpu.cfs_quota_us").write_text("200000\n", encoding="utf-8")
    (cpu / "cpu.cfs_period_us").write_text("100000\n", encoding="utf-8")
    assert (
        read_cgroup_cpu_quota(
            v2_max=tmp_path / "cpu.max",
            v1_quota=cpu / "cpu.cfs_quota_us",
            v1_period=cpu / "cpu.cfs_period_us",
        )
        == 2
    )


@pytest.mark.issue(750)
def test_cpuset_effective(tmp_path: Path) -> None:
    (tmp_path / "cpuset.cpus.effective").write_text("0-1\n", encoding="utf-8")
    assert (
        read_cpuset_cpus(
            paths=(
                tmp_path / "cpuset.cpus.effective",
                tmp_path / "cpuset.cpus",
                tmp_path / "cpuset" / "cpuset.cpus",
            )
        )
        == 2
    )


@pytest.mark.issue(750)
def test_detect_available_cpus_clamps_host_to_quota(tmp_path: Path) -> None:
    (tmp_path / "cpu.max").write_text("100000 100000\n", encoding="utf-8")
    available, quota, cpuset = detect_available_cpus(host_cpus=48, cgroup_root=tmp_path)
    assert available == 1
    assert quota == 1
    assert cpuset is None


@pytest.mark.issue(750)
def test_detect_available_cpus_unrestricted_host(tmp_path: Path) -> None:
    # Empty cgroup tree → no quota/cpuset → host count.
    available, quota, cpuset = detect_available_cpus(host_cpus=8, cgroup_root=tmp_path)
    assert available == 8
    assert quota is None
    assert cpuset is None


@pytest.mark.issue(750)
def test_explicit_workers_remain_authoritative(tmp_path: Path) -> None:
    (tmp_path / "cpu.max").write_text("100000 100000\n", encoding="utf-8")
    resolution = resolve_production_workers(4, host_cpus=48, cgroup_root=tmp_path)
    assert resolution.resolved == 4
    assert resolution.source == "explicit"
    assert resolution.quota_cpus == 1


@pytest.mark.issue(750)
def test_auto_mode_never_expands_past_quota(tmp_path: Path) -> None:
    (tmp_path / "cpu.max").write_text("100000 100000\n", encoding="utf-8")
    resolution = resolve_production_workers(0, host_cpus=48, cgroup_root=tmp_path, environ={})
    assert resolution.resolved == 1
    assert resolution.source == "cgroup_quota"
    assert "requested=0" in resolution.diagnostic_line()
    assert "resolved=1" in resolution.diagnostic_line()


@pytest.mark.issue(750)
def test_web_concurrency_overrides_auto(tmp_path: Path) -> None:
    (tmp_path / "cpu.max").write_text("100000 100000\n", encoding="utf-8")
    resolution = resolve_production_workers(
        0,
        host_cpus=48,
        cgroup_root=tmp_path,
        environ={"WEB_CONCURRENCY": "3"},
    )
    assert resolution.resolved == 3
    assert resolution.source == "web_concurrency"


@pytest.mark.issue(750)
def test_invalid_web_concurrency_ignored(tmp_path: Path) -> None:
    (tmp_path / "cpu.max").write_text("100000 100000\n", encoding="utf-8")
    resolution = resolve_production_workers(
        0,
        host_cpus=48,
        cgroup_root=tmp_path,
        environ={"WEB_CONCURRENCY": "nope"},
    )
    assert resolution.resolved == 1
    assert resolution.source == "cgroup_quota"


@pytest.mark.issue(750)
def test_emit_worker_resolution_writes_diagnostic() -> None:
    buf = StringIO()
    emit_worker_resolution(
        WorkerResolution(
            requested=0,
            resolved=1,
            source="cgroup_quota",
            host_cpus=48,
            quota_cpus=1,
            cpuset_cpus=None,
            platform_concurrency=None,
        ),
        stream=buf,
    )
    assert "chirp workers:" in buf.getvalue()
    assert "resolved=1" in buf.getvalue()


@pytest.mark.issue(750)
def test_production_launch_passes_resolved_workers_not_zero() -> None:
    app = App(AppConfig(debug=False, secret_key="test-secret", skip_contract_checks=True))

    captured: dict[str, object] = {}

    class FakeServer:
        def __init__(self, config, *args, **kwargs) -> None:
            captured["workers"] = config.workers

        def run(self) -> None:
            return None

    resolution = WorkerResolution(
        requested=0,
        resolved=1,
        source="cgroup_quota",
        host_cpus=48,
        quota_cpus=1,
        cpuset_cpus=None,
        platform_concurrency=None,
    )

    with (
        patch(
            "chirp.server.workers.resolve_production_workers",
            return_value=resolution,
        ),
        patch("chirp.server.workers.emit_worker_resolution"),
        patch("pounce.server.Server", FakeServer),
    ):
        from chirp.server.production import run_production_server

        run_production_server(app, workers=0)

    assert captured["workers"] == 1
