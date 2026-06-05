"""Tests for chirp.cli — CLI entrypoint and argument parsing."""

from types import SimpleNamespace

import pytest

from chirp.cli import main
from chirp.config import AppConfig


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


class TestCLIVersion:
    def test_version_flag_exits_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert out.startswith("chirp ")
        assert "kida" in out
        assert "Python" in out

    def test_short_version_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["-V"])
        assert exc_info.value.code == 0
        assert capsys.readouterr().out.startswith("chirp ")

    def test_version_report_matches_installed_version(self) -> None:
        import chirp
        from chirp.cli._version import version_report

        report = version_report()
        assert report.startswith(f"chirp {chirp.__version__} ")
        assert "bengal-pounce" in report


class TestCLINoCommand:
    def test_no_command_exits_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "chirp" in captured.out


class TestSecurityCheck:
    def test_wildcard_allowed_hosts_passes_in_development(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from chirp.cli import _security_check

        app = SimpleNamespace(
            config=AppConfig(
                env="development",
                allowed_hosts=("*",),
                secret_key="dev",
                csp_nonce_enabled=True,
            )
        )
        monkeypatch.setattr(_security_check, "resolve_app", lambda _import: app)

        with pytest.raises(SystemExit) as exc_info:
            _security_check.run_security_check(SimpleNamespace(app="app:app"))

        assert exc_info.value.code == 0
        assert "allowed_hosts configured (*)" in capsys.readouterr().out

    def test_wildcard_allowed_hosts_fails_outside_development(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from chirp.cli import _security_check

        app = SimpleNamespace(
            config=AppConfig(
                env="staging",
                allowed_hosts=("*",),
                secret_key="dev",
                csp_nonce_enabled=True,
            )
        )
        monkeypatch.setattr(_security_check, "resolve_app", lambda _import: app)

        with pytest.raises(SystemExit) as exc_info:
            _security_check.run_security_check(SimpleNamespace(app="app:app"))

        assert exc_info.value.code == 1
        assert 'allowed_hosts is "*" in staging' in capsys.readouterr().out
