"""Tests for chirp.cli._check — ``chirp check`` subcommand."""

import importlib.util
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from chirp import App, AppConfig
from chirp.cli import main


@pytest.fixture
def fake_check(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch App.check and register a fake module with an App instance."""
    mock_check = MagicMock()
    monkeypatch.setattr(App, "check", mock_check)

    app = App()
    mod = types.ModuleType("_check_test_app")
    mod.app = app  # type: ignore[attr-defined]
    monkeypatch.setitem(__import__("sys").modules, "_check_test_app", mod)
    return mock_check


class TestChirpCheck:
    def test_successful_check(self, fake_check: MagicMock) -> None:
        """check exits cleanly when App.check() succeeds."""
        fake_check.return_value = None
        main(["check", "_check_test_app:app"])
        fake_check.assert_called_once()

    def test_failed_check_exits_one(self, fake_check: MagicMock) -> None:
        """check exits 1 when App.check() raises SystemExit(1)."""
        fake_check.side_effect = SystemExit(1)
        with pytest.raises(SystemExit) as exc_info:
            main(["check", "_check_test_app:app"])
        assert exc_info.value.code == 1

    def test_warnings_as_errors_flag_is_forwarded(self, fake_check: MagicMock) -> None:
        """check forwards strict warning mode to App.check()."""
        fake_check.return_value = None
        main(["check", "_check_test_app:app", "--warnings-as-errors"])
        fake_check.assert_called_once_with(warnings_as_errors=True, coverage=False, deploy=False)

    def test_coverage_flag_is_forwarded(self, fake_check: MagicMock) -> None:
        """check forwards coverage reporting to App.check()."""
        fake_check.return_value = None
        main(["check", "_check_test_app:app", "--coverage"])
        fake_check.assert_called_once_with(warnings_as_errors=False, coverage=True, deploy=False)

    def test_deploy_flag_is_forwarded(self, fake_check: MagicMock) -> None:
        """check --deploy forwards production posture and implies strict warnings."""
        fake_check.return_value = None
        main(["check", "_check_test_app:app", "--deploy"])
        fake_check.assert_called_once_with(warnings_as_errors=True, coverage=False, deploy=True)

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
