"""Generated project metadata and development-only identities (#1060)."""

import json
import platform
import tomllib
from pathlib import Path

import pytest

from chirp.cli import main
from tests.cli.conftest import run_in_scaffold


@pytest.mark.issue(1060)
@pytest.mark.parametrize(
    "profile", ["minimal", "sse", "shell", "stream", "ai", "skill", "v2", "ui", "shell_ui"]
)
def test_generated_metadata_declares_existing_files(tmp_path: Path, monkeypatch, profile: str):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("chirp.cli._new._has_chirpui", lambda: True)
    flags = {"v2": [], "ui": ["--with-chirpui"], "shell_ui": ["--shell", "--with-chirpui"]}.get(
        profile, ["--" + profile]
    )
    main(["new", "project", *flags])
    project = tmp_path / "project"
    metadata = tomllib.loads((project / "pyproject.toml").read_text())
    assert (project / metadata["project"]["readme"]).is_file()
    assert (project / ".python-version").read_text().strip() == platform.python_version()
    assert metadata["project"]["requires-python"] == ">=3.14,<3.15"
    dependency = metadata["project"]["dependencies"][0]
    assert dependency.endswith(">=0.10.0,<0.11")
    assert "sessions" in dependency
    if profile in ("v2", "ui"):
        assert "auth" in dependency
        assert "forms" in dependency
    if profile in ("ui", "shell_ui"):
        assert "ui" in dependency
    build = metadata["tool"]["setuptools"]
    assert build["packages"] == []
    assert "app" in build["py-modules"]
    for module in build["py-modules"]:
        assert (project / (module + ".py")).is_file()
    for files in build["data-files"].values():
        assert all((project / file).is_file() for file in files)
    assert "uv sync --locked" in (project / "README.md").read_text()


@pytest.mark.issue(1060)
@pytest.mark.parametrize("environment", ["development", "staging", "production"])
def test_generated_demo_identity_is_development_only(tmp_path: Path, monkeypatch, environment: str):
    monkeypatch.chdir(tmp_path)
    main(["new", "project"])
    result = run_in_scaffold(
        tmp_path / "project",
        "import json; from models import verify_user; print(json.dumps(verify_user('admin', 'password') is not None))",
        extra_env={"CHIRP_ENV": environment},
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) is (environment == "development")


@pytest.mark.issue(1060)
@pytest.mark.parametrize("profile", ["minimal", "shell", "v2"])
def test_generated_app_uses_canonical_stack(tmp_path: Path, monkeypatch, profile: str):
    monkeypatch.chdir(tmp_path)
    main(["new", "project", *([] if profile == "v2" else ["--" + profile])])
    source = (tmp_path / "project" / "app.py").read_text()
    assert "for middleware in secure_stack(config" in source
    assert "SessionMiddleware(" not in source


@pytest.mark.issue(1060)
@pytest.mark.parametrize("profile", ["sse", "stream", "ai", "skill", "v2"])
def test_generated_smoke_tests_pass(tmp_path: Path, monkeypatch, profile: str):
    import os
    import subprocess
    import sys

    monkeypatch.chdir(tmp_path)
    main(["new", "project", *([] if profile == "v2" else ["--" + profile])])
    project = tmp_path / "project"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-q"],
        cwd=project,
        env={
            **os.environ,
            "CHIRP_SECRET_KEY": "scaffold-test-secret-at-least-32-characters",
            "PYTHONPATH": str(project) + os.pathsep + os.environ.get("PYTHONPATH", ""),
            "CHIRP_ENV": "development",
        },
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.issue(1060)
@pytest.mark.parametrize("profile", ["minimal", "sse", "shell", "stream", "ai", "skill", "v2"])
def test_generated_wheel_contains_modules_and_assets(tmp_path: Path, monkeypatch, profile: str):
    import subprocess
    import sys
    from zipfile import ZipFile

    pytest.importorskip("setuptools")
    monkeypatch.chdir(tmp_path)
    main(["new", "project", *([] if profile == "v2" else ["--" + profile])])
    project = tmp_path / "project"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            'from setuptools.build_meta import build_wheel; build_wheel("dist")',
        ],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    with ZipFile(next((project / "dist").glob("*.whl"))) as wheel:
        names = wheel.namelist()
    assert "app.py" in names
    assert "project_paths.py" in names
    assert any(".data/data/share/project/" in name and name.endswith(".html") for name in names)


@pytest.mark.issue(1060)
@pytest.mark.parametrize("with_ui", [False, True])
def test_shell_scaffold_renders_page_context(tmp_path: Path, monkeypatch, with_ui: bool):
    if with_ui:
        pytest.importorskip("chirp_ui")
    monkeypatch.chdir(tmp_path)
    main(["new", "project", "--shell", *(["--with-chirpui"] if with_ui else [])])
    result = run_in_scaffold(
        tmp_path / "project",
        """import asyncio
from app import app
from chirp.testing import TestClient
async def smoke():
    async with TestClient(app) as client:
        for route in ("/", "/items"):
            response = await client.get(route)
            assert response.status == 200, response.text
asyncio.run(smoke())
""",
    )
    assert result.returncode == 0, result.stdout + result.stderr
