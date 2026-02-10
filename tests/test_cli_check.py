"""Tests for chirp.cli._check — ``chirp check`` subcommand."""

import types
from unittest.mock import MagicMock

import pytest

from chirp.app import App
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

    def test_invalid_import_string(self, capsys: pytest.CaptureFixture[str]) -> None:
        """check exits 1 with error message for bad import string."""
        with pytest.raises(SystemExit) as exc_info:
            main(["check", "nonexistent_module_xyz:app"])
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error:" in captured.err
