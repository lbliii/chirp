"""Tests for chirp.cli._new — ``chirp new`` subcommand."""

from pathlib import Path

import pytest

from chirp.cli import main


def test_templates_shim_import() -> None:
    """chirp.cli._templates re-exports from chirp.cli.templates for backward compat."""
    from chirp.cli._templates import STYLE_CSS, V2_APP_PY

    assert "box-sizing" in STYLE_CSS
    assert "App(" in V2_APP_PY


class TestChirpNewDefaultV2:
    def test_creates_expected_v2_tree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Default scaffold (v2) creates pages/, static/, tests/, models.py."""
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp"])

        project = tmp_path / "myapp"
        assert (project / "app.py").is_file()
        assert (project / "models.py").is_file()
        assert (project / "pages" / "_layout.html").is_file()
        assert (project / "pages" / "page.py").is_file()
        assert (project / "pages" / "page.html").is_file()
        assert (project / "pages" / "login" / "page.py").is_file()
        assert (project / "pages" / "login" / "page.html").is_file()
        assert (project / "pages" / "dashboard" / "page.py").is_file()
        assert (project / "pages" / "dashboard" / "page.html").is_file()
        assert (project / "static" / "style.css").is_file()
        assert (project / "static" / "theme.css").is_file()
        assert (project / "pyproject.toml").is_file()
        assert (project / "migrations" / ".gitkeep").is_file()
        assert (project / "tests" / "conftest.py").is_file()
        assert (project / "tests" / "test_app.py").is_file()

    def test_generated_v2_app_contains_security_defaults(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp"])

        source = (tmp_path / "myapp" / "app.py").read_text()
        assert "CHIRP_SECRET_KEY" in source
        assert "Refusing to start in production with default secret key" in source
        assert "secure=not config.debug" in source
        assert "CSRFMiddleware(CSRFConfig())" in source
        assert "SecurityHeadersMiddleware()" in source

    def test_generated_v2_files_are_valid_python(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp"])

        app_source = (tmp_path / "myapp" / "app.py").read_text()
        models_source = (tmp_path / "myapp" / "models.py").read_text()
        test_source = (tmp_path / "myapp" / "tests" / "test_app.py").read_text()

        compile(app_source, "app.py", "exec")
        compile(models_source, "models.py", "exec")
        compile(test_source, "test_app.py", "exec")

    def test_prints_success_message_and_login_hint(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp"])

        captured = capsys.readouterr()
        assert "Created project 'myapp'" in captured.out
        assert "Login: admin / password" in captured.out


class TestChirpNewMinimal:
    def test_creates_minimal_tree(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--minimal creates only app.py and templates/index.html."""
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp", "--minimal"])

        project = tmp_path / "myapp"
        assert (project / "app.py").is_file()
        assert (project / "templates" / "index.html").is_file()
        assert not (project / "pages").exists()
        assert not (project / "static").exists()
        assert not (project / "tests").exists()

    def test_minimal_app_is_valid_python(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp", "--minimal"])

        source = (tmp_path / "myapp" / "app.py").read_text()
        compile(source, "app.py", "exec")


class TestChirpNewSSE:
    def test_creates_sse_tree(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp", "--sse"])

        project = tmp_path / "myapp"
        assert (project / "app.py").is_file()
        assert (project / "templates" / "index.html").is_file()
        assert (project / "static" / "style.css").is_file()
        assert (project / "tests" / "test_app.py").is_file()


class TestChirpNewShell:
    def test_creates_shell_tree(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--shell creates persistent app shell with layout, items inner shell."""
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp", "--shell"])

        project = tmp_path / "myapp"
        assert (project / "app.py").is_file()
        assert (project / "pages" / "_context.py").is_file()
        assert (project / "pages" / "_layout.html").is_file()
        assert (project / "pages" / "page.py").is_file()
        assert (project / "pages" / "page.html").is_file()
        assert (project / "pages" / "items" / "_layout.html").is_file()
        assert (project / "pages" / "items" / "page.py").is_file()
        assert (project / "pages" / "items" / "page.html").is_file()
        assert (project / "pyproject.toml").is_file()
        assert (project / "static" / "theme.css").is_file()

    def test_shell_app_is_valid_python(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp", "--shell"])

        app_source = (tmp_path / "myapp" / "app.py").read_text()
        context_source = (tmp_path / "myapp" / "pages" / "_context.py").read_text()
        compile(app_source, "app.py", "exec")
        compile(context_source, "_context.py", "exec")


class TestChirpNewGuards:
    def test_existing_directory_exits_one(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Refuse to overwrite an existing directory."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "myapp").mkdir()

        with pytest.raises(SystemExit) as exc_info:
            main(["new", "myapp"])
        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "already exists" in captured.err
