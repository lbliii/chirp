"""Capability-lane skip-fail policy (#917).

Proves the registry helpers and that specialized lanes fail closed on
unexpected skips / missing collection without affecting ordinary local runs.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.capability.lanes import (
    CAPABILITY_LANE_ENV,
    LANE_REGISTRY,
    CapabilityLane,
    format_collection_failure,
    format_skip_failure,
    get_lane,
    is_allowed_skip,
    missing_required_selectors,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CI_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "ci.yml"

# Specialized ci.yml jobs that must declare CHIRP_CAPABILITY_LANE.
_EXPECTED_CI_LANES = (
    "auth-capability",
    "redis-capability",
    "config-capability",
    "ai-bedrock-capability",
    "browser-smoke",
    "query-interop",
    "test-postgres",
    "data-pg-gil-gate",
    "chirp-ui-compat",
    "chirp-ui-compat-shells",
)


@pytest.mark.issue(917)
def test_registry_covers_specialized_ci_lanes() -> None:
    for name in _EXPECTED_CI_LANES:
        assert name in LANE_REGISTRY, f"missing lane registry entry for {name!r}"
        lane = LANE_REGISTRY[name]
        assert lane.name == name
        assert lane.capability
        assert lane.install_hint
        assert lane.required_selectors, f"{name} must declare required selectors"


@pytest.mark.issue(917)
def test_ci_yml_opts_every_specialized_lane_into_skip_fail() -> None:
    text = _CI_WORKFLOW.read_text(encoding="utf-8")
    assert "auth-capability:" in text
    for name in _EXPECTED_CI_LANES:
        needle = f'{CAPABILITY_LANE_ENV}: "{name}"'
        assert needle in text, (
            f"ci.yml must set {needle} on the specialized pytest step (lane={name!r})"
        )


@pytest.mark.issue(917)
def test_get_lane_unknown_names_fail_loud() -> None:
    with pytest.raises(KeyError, match="unknown capability lane"):
        get_lane("not-a-real-lane")


@pytest.mark.issue(917)
def test_missing_required_selectors_are_named() -> None:
    lane = CapabilityLane(
        name="demo",
        capability="demo-capability",
        install_hint="install demo",
        required_selectors=("Alpha::", "Beta::"),
    )
    missing = missing_required_selectors(lane, ["tests/x.py::Alpha::test_one"])
    assert missing == ["Beta::"]
    message = format_collection_failure(lane, missing)
    assert "demo-capability" in message
    assert "install demo" in message
    assert "Beta::" in message


@pytest.mark.issue(917)
def test_allowed_skip_substring_matching() -> None:
    lane = CapabilityLane(
        name="demo",
        capability="demo-capability",
        install_hint="install demo",
        required_selectors=("x",),
        allowed_skip_reason_substrings=("Alpine runtime not available",),
    )
    assert is_allowed_skip(lane, "chirp-ui Alpine runtime not available in this version")
    assert not is_allowed_skip(lane, "CHIRP_TEST_PG_DSN not set")


@pytest.mark.issue(917)
def test_skip_failure_diagnostics_name_capability() -> None:
    lane = CapabilityLane(
        name="auth-capability",
        capability="chirp[auth] / argon2-cffi",
        install_hint="uv sync --extra auth",
        required_selectors=("TestArgon2::",),
    )
    message = format_skip_failure(
        lane,
        [("tests/test_passwords.py::TestArgon2::test_x", "argon2-cffi not installed")],
    )
    assert "auth-capability" in message
    assert "argon2-cffi not installed" in message
    assert "chirp[auth] / argon2-cffi" in message
    assert "uv sync --extra auth" in message


@pytest.mark.issue(917)
def test_unset_env_keeps_soft_skips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ordinary runs without CHIRP_CAPABILITY_LANE must not fail on skips."""
    monkeypatch.delenv(CAPABILITY_LANE_ENV, raising=False)
    test_file = tmp_path / "test_soft_skip.py"
    test_file.write_text(
        "import pytest\n\ndef test_optional():\n    pytest.skip('optional missing')\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file), "-q", "--tb=no"],
        cwd=_REPO_ROOT,
        env={k: v for k, v in os.environ.items() if k != CAPABILITY_LANE_ENV},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "skipped" in (result.stdout + result.stderr).lower() or "1 skipped" in (
        result.stdout + result.stderr
    )


@pytest.mark.issue(917)
def test_lane_env_fails_on_unexpected_skip(tmp_path: Path) -> None:
    """A registered lane with no allowed skips turns soft skips into failures."""
    helper = tmp_path / "lane_probe.py"
    helper.write_text(
        """\
import os
import sys
from pathlib import Path

import pytest

repo = Path(sys.argv[1])
os.chdir(repo)
sys.path.insert(0, str(repo))

from tests.capability import lanes as lanes_mod
from tests.capability.lanes import CapabilityLane

lanes_mod.LANE_REGISTRY["probe-lane"] = CapabilityLane(
    name="probe-lane",
    capability="probe-infra",
    install_hint="install probe-infra",
    required_selectors=("test_probe.py::test_required",),
)

probe = Path(sys.argv[2])
os.environ["CHIRP_CAPABILITY_LANE"] = "probe-lane"
raise SystemExit(
    pytest.main([str(probe), "-p", "tests.capability.plugin", "-q", "--tb=line"])
)
""",
        encoding="utf-8",
    )
    probe = tmp_path / "test_probe.py"
    probe.write_text(
        "import pytest\n\ndef test_required():\n    pytest.skip('probe-infra not installed')\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(helper), str(_REPO_ROOT), str(probe)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, result.stdout + result.stderr
    combined = result.stdout + result.stderr
    assert "probe-infra" in combined
    assert "unexpected skips" in combined or "skip-fail" in combined


@pytest.mark.issue(917)
def test_lane_env_fails_when_required_selector_missing(tmp_path: Path) -> None:
    helper = tmp_path / "lane_probe_missing.py"
    helper.write_text(
        """\
import os
import sys
from pathlib import Path

import pytest

repo = Path(sys.argv[1])
os.chdir(repo)
sys.path.insert(0, str(repo))

from tests.capability import lanes as lanes_mod
from tests.capability.lanes import CapabilityLane

lanes_mod.LANE_REGISTRY["probe-missing"] = CapabilityLane(
    name="probe-missing",
    capability="missing-selector-infra",
    install_hint="install missing-selector-infra",
    required_selectors=("DefinitelyMissingSelector::",),
)

probe = Path(sys.argv[2])
os.environ["CHIRP_CAPABILITY_LANE"] = "probe-missing"
raise SystemExit(
    pytest.main([str(probe), "-p", "tests.capability.plugin", "-q", "--tb=line"])
)
""",
        encoding="utf-8",
    )
    probe = tmp_path / "test_unrelated.py"
    probe.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(helper), str(_REPO_ROOT), str(probe)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, result.stdout + result.stderr
    combined = result.stdout + result.stderr
    assert "DefinitelyMissingSelector::" in combined
    assert "missing-selector-infra" in combined
