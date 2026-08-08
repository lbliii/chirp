"""Acceptance coverage for fresh-environment install smoke (#910)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
WORKFLOW = ROOT / ".github" / "workflows" / "install-smoke.yml"
DECISION = ROOT / "plan" / "drafted" / "decision-908-dependency-resolution-profiles.md"
DOCS = ROOT / "docs" / "dependency-resolution-profiles.md"

sys.path.insert(0, str(SCRIPTS))
from dependency_profiles import (  # noqa: E402
    PROFILE_BY_ID,
    SUPPORTED_PROFILES,
    ci_matrix_entries,
)
from install_smoke import InstallSmokeError, _smoke_source  # noqa: E402

# Decision #908 supported profile IDs (finite matrix — not a Cartesian product).
EXPECTED_PROFILE_IDS = frozenset(
    {
        "minimal",
        "dev",
        "docs",
        "browser",
        "benchmark",
        "full",
        "all",
        "extra-forms",
        "extra-sessions",
        "extra-auth",
        "extra-passkeys",
        "extra-testing",
        "extra-data-pg",
        "extra-ai",
        "extra-ai-bedrock",
        "extra-markdown",
        "extra-ui",
        "extra-config",
        "extra-redis",
        "chirp-ui-compat",
    }
)


@pytest.mark.issue(910)
def test_supported_profiles_match_decision_matrix() -> None:
    """The machine-readable matrix covers every decision #908 profile ID."""
    assert frozenset(PROFILE_BY_ID) == EXPECTED_PROFILE_IDS
    assert len(SUPPORTED_PROFILES) == len(EXPECTED_PROFILE_IDS)
    decision = DECISION.read_text(encoding="utf-8")
    for profile_id in EXPECTED_PROFILE_IDS:
        assert f"`{profile_id}`" in decision, f"missing decision row for {profile_id}"


@pytest.mark.issue(910)
def test_each_profile_names_resolution_and_import_smoke() -> None:
    for profile in SUPPORTED_PROFILES:
        assert profile.resolution.strip(), profile.id
        assert profile.import_modules, profile.id
        assert profile.id in profile.resolution or "uv sync" in profile.resolution


@pytest.mark.issue(910)
def test_minimal_and_dev_cover_gil_and_free_threaded_python() -> None:
    """Required Python variants: 3.14 + free-threaded 3.14t for core profiles."""
    assert PROFILE_BY_ID["minimal"].python == ("3.14", "3.14t")
    assert PROFILE_BY_ID["dev"].python == ("3.14", "3.14t")
    for profile in SUPPORTED_PROFILES:
        assert "3.14t" in profile.python, profile.id


@pytest.mark.issue(910)
def test_failure_message_names_profile_and_resolution_path() -> None:
    profile = PROFILE_BY_ID["extra-redis"]
    err = InstallSmokeError(profile, "import", "ModuleNotFoundError: No module named 'redis'")
    text = str(err)
    assert "extra-redis" in text
    assert profile.resolution in text
    assert "import" in text
    assert "ModuleNotFoundError" in text


@pytest.mark.issue(910)
def test_ci_matrix_json_is_stable_and_includes_python_variants() -> None:
    entries = ci_matrix_entries()
    assert entries
    profiles = {e["profile"] for e in entries}
    assert profiles == EXPECTED_PROFILE_IDS
    minimal_py = {e["python-version"] for e in entries if e["profile"] == "minimal"}
    assert minimal_py == {"3.14", "3.14t"}
    # CLI must emit the same payload the workflow consumes.
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "install_smoke.py"), "--matrix-json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(proc.stdout) == entries


@pytest.mark.issue(910)
def test_install_smoke_workflow_is_dedicated_and_wired() -> None:
    """Prefer a dedicated install-smoke workflow over bloating capability lanes."""
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "name: Install smoke" in workflow
    assert "scripts/install_smoke.py" in workflow
    assert "--profile ${{ matrix.profile }}" in workflow
    assert "--python ${{ matrix.python-version }}" in workflow
    assert "fromJson(needs.matrix.outputs.include)" in workflow
    # Stay out of specialized capability lanes owned by sibling issues.
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "install_smoke.py" not in ci
    assert "install-smoke:" not in ci


@pytest.mark.issue(910)
def test_maintained_docs_surface_points_at_command_and_workflow() -> None:
    docs = DOCS.read_text(encoding="utf-8")
    assert "install-smoke" in docs
    assert "scripts/install_smoke.py" in docs
    assert "#910" in docs or "issue 910" in docs.lower()
    for profile_id in ("minimal", "dev", "extra-redis", "chirp-ui-compat"):
        assert f"`{profile_id}`" in docs


@pytest.mark.issue(910)
def test_smoke_source_imports_intended_modules() -> None:
    source = _smoke_source(PROFILE_BY_ID["full"])
    assert "import multipart" in source
    assert "import argon2" in source
    assert "print('ok')" in source
