"""Tests for chirp.cli._check — ``chirp check`` subcommand."""

import importlib.util
import json
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from chirp import App, AppConfig
from chirp.cli import main
from chirp.contracts import CheckResult, ContractIssue, Severity, result_to_dict


@pytest.fixture
def fake_check(monkeypatch: pytest.MonkeyPatch) -> tuple[MagicMock, CheckResult, App]:
    """Patch the structured contract collector and register a fake app."""
    result = CheckResult(routes_checked=1)
    app = App()
    mod = types.ModuleType("_check_test_app")
    mod.app = app  # type: ignore[attr-defined]
    monkeypatch.setitem(__import__("sys").modules, "_check_test_app", mod)

    def collect(
        _app: App,
        *,
        deploy: bool,
        include_info: bool,
        include_coverage: bool,
    ) -> tuple[CheckResult, dict[str, object]]:
        return result, result_to_dict(
            result,
            include_info=include_info,
            include_coverage=include_coverage,
        )

    mock_collect = MagicMock(side_effect=collect)
    monkeypatch.setattr("chirp.cli._check.collect_check_json", mock_collect)
    return mock_collect, result, app


class TestChirpCheck:
    def test_successful_check(self, fake_check: tuple[MagicMock, CheckResult, App]) -> None:
        """check exits cleanly when the structured result succeeds."""
        collector, _, app = fake_check
        main(["check", "_check_test_app:app"])
        collector.assert_called_once_with(
            app,
            deploy=False,
            include_info=False,
            include_coverage=False,
        )

    def test_failed_check_exits_one(self, fake_check: tuple[MagicMock, CheckResult, App]) -> None:
        """check exits 1 when the structured result contains an error."""
        _, result, _ = fake_check
        result.issues.append(ContractIssue(Severity.ERROR, "test", "broken"))
        with pytest.raises(SystemExit) as exc_info:
            main(["check", "_check_test_app:app"])
        assert exc_info.value.code == 1

    def test_warnings_as_errors_flag_changes_exit_policy(
        self, fake_check: tuple[MagicMock, CheckResult, App]
    ) -> None:
        """check applies strict warning policy to the structured result."""
        _, result, _ = fake_check
        result.issues.append(ContractIssue(Severity.WARNING, "test", "review me"))
        with pytest.raises(SystemExit) as exc_info:
            main(["check", "_check_test_app:app", "--warnings-as-errors"])
        assert exc_info.value.code == 1

    def test_coverage_flag_is_forwarded(
        self, fake_check: tuple[MagicMock, CheckResult, App]
    ) -> None:
        """check requests coverage in the structured payload."""
        collector, _, app = fake_check
        main(["check", "_check_test_app:app", "--coverage"])
        collector.assert_called_once_with(
            app,
            deploy=False,
            include_info=False,
            include_coverage=True,
        )

    def test_json_coverage_is_opt_in(
        self,
        fake_check: tuple[MagicMock, CheckResult, App],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        main(["check", "_check_test_app:app", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert "coverage" not in payload

    def test_json_coverage_includes_webmcp_counters(
        self,
        fake_check: tuple[MagicMock, CheckResult, App],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        main(["check", "_check_test_app:app", "--json", "--coverage"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["coverage"]["webmcp_projections_declared"] == 0
        assert payload["coverage"]["webmcp_projections_compiled"] == 0
        assert payload["coverage"]["webmcp_parameters_declared"] == 0

    def test_deploy_flag_is_forwarded(self, fake_check: tuple[MagicMock, CheckResult, App]) -> None:
        """check --deploy requests production posture."""
        collector, _, app = fake_check
        main(["check", "_check_test_app:app", "--deploy"])
        collector.assert_called_once_with(
            app,
            deploy=True,
            include_info=False,
            include_coverage=False,
        )

    def test_invalid_import_string(self, capsys: pytest.CaptureFixture[str]) -> None:
        """check exits 1 with error message for bad import string."""
        with pytest.raises(SystemExit) as exc_info:
            main(["check", "nonexistent_module_xyz:app"])
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error:" in captured.err

    def test_hackernews_app_passes_check(self) -> None:
        """Hacker News example (boost layout + SSE) passes chirp check."""
        app_path = (
            Path(__file__).resolve().parent.parent
            / "examples"
            / "standalone"
            / "hackernews"
            / "app.py"
        )
        if not app_path.exists():
            pytest.skip("examples/standalone/hackernews not found")
        spec = importlib.util.spec_from_file_location("hackernews_app", app_path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        app = module.app
        app.check()  # raises SystemExit(1) on failure

    def test_deploy_posture_escalates_dev_safe_app(self) -> None:
        """An app that passes in development fails under --deploy posture.

        Empty secret_key + permissive allowed_hosts + a mutating route with no
        security stack are silent/WARNING in development, so plain check()
        passes. Under deploy posture (production view) they escalate to ERROR
        and check(deploy=True) raises SystemExit(1) — without mutating the app.
        """
        config = AppConfig(
            env="development",
            secret_key="",
            allowed_hosts=("*",),
        )
        app = App(config)

        @app.route("/save", methods=["POST"])
        async def save() -> str:  # pragma: no cover - never invoked
            return "ok"

        app.freeze()

        # Development posture: passes (no ERROR; warnings tolerated).
        app.check()

        # Deploy posture: production-severity rules escalate to ERROR.
        with pytest.raises(SystemExit) as exc_info:
            app.check(deploy=True)
        assert exc_info.value.code == 1

        # The real config is never mutated by the posture view.
        assert app.config.env == "development"
        assert app.config.secret_key == ""
