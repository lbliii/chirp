"""Tests for chirp.cli._new — ``chirp new`` subcommand."""

import os
from pathlib import Path

import pytest

from chirp.cli import main


class TestChirpNewDefault:
    def test_creates_expected_tree(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default scaffold creates app.py, templates/, static/, tests/."""
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp"])

        project = tmp_path / "myapp"
        assert (project / "app.py").is_file()
        assert (project / "templates" / "base.html").is_file()
        assert (project / "templates" / "index.html").is_file()
        assert (project / "static" / "style.css").is_file()
        assert (project / "tests" / "test_app.py").is_file()

    def test_app_py_is_valid_python(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Generated app.py is syntactically valid Python."""
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp"])

        source = (tmp_path / "myapp" / "app.py").read_text()
        compile(source, "app.py", "exec")  # Raises SyntaxError if invalid

    def test_test_app_is_valid_python(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Generated test_app.py is syntactically valid Python."""
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp"])

        source = (tmp_path / "myapp" / "tests" / "test_app.py").read_text()
        compile(source, "test_app.py", "exec")

    def test_prints_success_message(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp"])

        captured = capsys.readouterr()
        assert "Created project 'myapp'" in captured.out


class TestChirpNewMinimal:
    def test_creates_minimal_tree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--minimal creates only app.py and templates/index.html."""
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp", "--minimal"])

        project = tmp_path / "myapp"
        assert (project / "app.py").is_file()
        assert (project / "templates" / "index.html").is_file()
        # These should NOT exist in minimal mode
        assert not (project / "templates" / "base.html").exists()
        assert not (project / "static").exists()
        assert not (project / "tests").exists()

    def test_minimal_app_is_valid_python(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        main(["new", "myapp", "--minimal"])

        source = (tmp_path / "myapp" / "app.py").read_text()
        compile(source, "app.py", "exec")


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
