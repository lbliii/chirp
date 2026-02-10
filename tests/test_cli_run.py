"""Tests for chirp.cli._run — ``chirp run`` subcommand."""

import types
from unittest.mock import MagicMock, patch

import pytest

from chirp.app import App
from chirp.cli import main
from chirp.config import AppConfig


@pytest.fixture
def fake_app(monkeypatch: pytest.MonkeyPatch) -> App:
    """Register a fake module with a chirp App instance."""
    app = App(config=AppConfig(host="127.0.0.1", port=8000, debug=True))
    mod = types.ModuleType("_run_test_app")
    mod.app = app  # type: ignore[attr-defined]
    monkeypatch.setitem(__import__("sys").modules, "_run_test_app", mod)
    return app


class TestChirpRun:
    @patch("chirp.server.dev.run_dev_server")
    def test_default_host_and_port(
        self, mock_server: MagicMock, fake_app: App
    ) -> None:
        """run uses app config defaults when --host/--port are omitted."""
        main(["run", "_run_test_app:app"])
        mock_server.assert_called_once()
        args = mock_server.call_args[0]
        assert args[0] is fake_app
        assert args[1] == "127.0.0.1"
        assert args[2] == 8000

    @patch("chirp.server.dev.run_dev_server")
    def test_host_override(self, mock_server: MagicMock, fake_app: App) -> None:
        """--host overrides the app config."""
        main(["run", "_run_test_app:app", "--host", "0.0.0.0"])
        args = mock_server.call_args[0]
        assert args[1] == "0.0.0.0"

    @patch("chirp.server.dev.run_dev_server")
    def test_port_override(self, mock_server: MagicMock, fake_app: App) -> None:
        """--port overrides the app config."""
        main(["run", "_run_test_app:app", "--port", "3000"])
        args = mock_server.call_args[0]
        assert args[2] == 3000

    @patch("chirp.server.dev.run_dev_server")
    def test_app_path_forwarded(self, mock_server: MagicMock, fake_app: App) -> None:
        """The original import string is passed as app_path for reload."""
        main(["run", "_run_test_app:app"])
        kwargs = mock_server.call_args[1]
        assert kwargs["app_path"] == "_run_test_app:app"

    @patch("chirp.server.dev.run_dev_server")
    def test_reload_from_config(self, mock_server: MagicMock, fake_app: App) -> None:
        """reload flag comes from app.config.debug."""
        main(["run", "_run_test_app:app"])
        kwargs = mock_server.call_args[1]
        assert kwargs["reload"] is True  # debug=True in fixture

    def test_invalid_import_string(self, capsys: pytest.CaptureFixture[str]) -> None:
        """run exits 1 with error message for bad import string."""
        with pytest.raises(SystemExit) as exc_info:
            main(["run", "nonexistent_module_xyz:app"])
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error:" in captured.err
