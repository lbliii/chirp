"""Tests for chirp.cli — CLI entrypoint and argument parsing."""

import pytest

from chirp.cli import main


class TestCLIHelp:
    def test_help_exits_zero(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0

    def test_new_help_exits_zero(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["new", "--help"])
        assert exc_info.value.code == 0

    def test_run_help_exits_zero(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["run", "--help"])
        assert exc_info.value.code == 0

    def test_check_help_exits_zero(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["check", "--help"])
        assert exc_info.value.code == 0


class TestCLIMissingArgs:
    def test_new_missing_name(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["new"])
        assert exc_info.value.code == 2

    def test_run_missing_app(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["run"])
        assert exc_info.value.code == 2

    def test_check_missing_app(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["check"])
        assert exc_info.value.code == 2


class TestCLINoCommand:
    def test_no_command_exits_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "chirp" in captured.out
