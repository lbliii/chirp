"""Tests for startup error formatting and integration with server/CLI paths."""

import errno
import types
from unittest.mock import MagicMock, patch

import pytest
from pounce import LifespanError, PounceError, TLSError

from chirp.server.terminal_errors import format_startup_error

# ---------------------------------------------------------------------------
# Unit tests: format_startup_error
# ---------------------------------------------------------------------------


class TestFormatStartupError:
    """format_startup_error returns actionable messages for known errors."""

    def test_port_in_use_eaddrinuse(self) -> None:
        exc = OSError(errno.EADDRINUSE, "Address already in use")
        msg = format_startup_error(exc)
        assert msg is not None
        assert "already in use" in msg.lower() or "Error:" in msg
        assert "app.run(port=8001)" in msg

    def test_port_in_use_cli_hint(self) -> None:
        exc = OSError(errno.EADDRINUSE, "Address already in use")
        msg = format_startup_error(exc, cli=True)
        assert msg is not None
        assert "chirp run" in msg
        assert "--port 8001" in msg
        assert "app.run" not in msg

    def test_port_in_use_string_match(self) -> None:
        exc = OSError("Address already in use")
        msg = format_startup_error(exc)
        assert msg is not None
        assert "app.run(port=8001)" in msg

    def test_permission_denied(self) -> None:
        exc = OSError(errno.EACCES, "Permission denied")
        msg = format_startup_error(exc)
        assert msg is not None
        assert "Error:" in msg
        assert "1024" in msg or "elevated" in msg

    def test_other_oserror(self) -> None:
        exc = OSError(errno.ECONNREFUSED, "Connection refused")
        msg = format_startup_error(exc)
        assert msg is not None
        assert "Error:" in msg

    def test_pounce_error(self) -> None:
        exc = LifespanError("startup hook failed")
        msg = format_startup_error(exc)
        assert msg is not None
        assert "startup hook failed" in msg

    def test_pounce_tls_error(self) -> None:
        exc = TLSError("bad cert")
        msg = format_startup_error(exc)
        assert msg is not None
        assert "bad cert" in msg

    def test_pounce_error_with_cause(self) -> None:
        cause = ConnectionRefusedError("DB refused connection on port 5432")
        try:
            raise LifespanError("Application startup failed") from cause
        except LifespanError as exc:
            msg = format_startup_error(exc)
        assert msg is not None
        assert "Application startup failed" in msg
        assert "Caused by:" in msg
        assert "ConnectionRefusedError" in msg
        assert "5432" in msg

    def test_pounce_error_without_cause_has_no_caused_by(self) -> None:
        exc = LifespanError("startup hook failed")
        msg = format_startup_error(exc)
        assert msg is not None
        assert "Caused by:" not in msg

    def test_configuration_error(self) -> None:
        from chirp.errors import ConfigurationError

        exc = ConfigurationError("invalid host")
        msg = format_startup_error(exc)
        assert msg is not None
        assert "Configuration error" in msg
        assert "invalid host" in msg

    def test_value_error(self) -> None:
        exc = ValueError("port must be positive")
        msg = format_startup_error(exc)
        assert msg is not None
        assert "Configuration error" in msg
        assert "port must be positive" in msg

    def test_unknown_error_returns_none(self) -> None:
        exc = RuntimeError("something unexpected")
        assert format_startup_error(exc) is None

    def test_type_error_returns_none(self) -> None:
        exc = TypeError("bad argument")
        assert format_startup_error(exc) is None

    def test_pounce_oserror_not_treated_as_socket_error(self) -> None:
        """PounceError subclasses that also inherit OSError should go
        through the PounceError branch, not the OSError branch."""

        class SocketPounceError(PounceError, OSError):
            pass

        exc = SocketPounceError("mixed")
        msg = format_startup_error(exc)
        assert msg is not None
        assert "Error:" in msg
        assert "app.run(port=8001)" not in msg


# ---------------------------------------------------------------------------
# Integration: ServerLauncher.run() wiring
# ---------------------------------------------------------------------------


class TestServerLauncherErrorHandling:
    """ServerLauncher.run() catches startup errors and formats them."""

    def _make_launcher(self) -> object:
        from chirp.app.server import ServerLauncher
        from chirp.app.state import MutableAppState
        from chirp.config import AppConfig

        config = AppConfig(host="127.0.0.1", port=8000, debug=True)
        return ServerLauncher(config, MutableAppState())

    @patch("chirp.server.dev.run_dev_server")
    def test_known_error_prints_to_stderr_and_exits(
        self, mock_dev: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_dev.side_effect = OSError(errno.EADDRINUSE, "Address already in use")
        launcher = self._make_launcher()

        with pytest.raises(SystemExit) as exc_info:
            launcher.run(MagicMock(), host=None, port=None, lifecycle_collector=None)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "already in use" in captured.err.lower()
        assert "app.run(port=8001)" in captured.err

    @patch("chirp.server.dev.run_dev_server")
    def test_unknown_error_re_raises(self, mock_dev: MagicMock) -> None:
        mock_dev.side_effect = RuntimeError("boom")
        launcher = self._make_launcher()

        with pytest.raises(RuntimeError, match="boom"):
            launcher.run(MagicMock(), host=None, port=None, lifecycle_collector=None)

    @patch("chirp.server.dev.run_dev_server")
    def test_full_traceback_skips_formatted_message(
        self,
        mock_dev: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """CHIRP_TRACEBACK=full should re-raise without printing the formatted message."""
        monkeypatch.setenv("CHIRP_TRACEBACK", "full")
        mock_dev.side_effect = OSError(errno.EADDRINUSE, "Address already in use")
        launcher = self._make_launcher()

        with pytest.raises(OSError, match="Address already in use"):
            launcher.run(MagicMock(), host=None, port=None, lifecycle_collector=None)

        captured = capsys.readouterr()
        assert captured.err == ""  # No formatted output — full traceback from Python

    @patch("chirp.server.dev.run_dev_server")
    def test_keyboard_interrupt_is_silent(
        self, mock_dev: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_dev.side_effect = KeyboardInterrupt
        launcher = self._make_launcher()

        launcher.run(MagicMock(), host=None, port=None, lifecycle_collector=None)

        captured = capsys.readouterr()
        assert captured.err == ""


# ---------------------------------------------------------------------------
# Integration: chirp run CLI wiring
# ---------------------------------------------------------------------------


class TestCliRunErrorHandling:
    """run_server() catches startup errors with cli=True hints."""

    @pytest.fixture
    def fake_app(self, monkeypatch: pytest.MonkeyPatch) -> object:
        from chirp import App
        from chirp.config import AppConfig

        app = App(config=AppConfig(host="127.0.0.1", port=8000, debug=True))
        mod = types.ModuleType("_startup_err_test_app")
        mod.app = app  # type: ignore[attr-defined]
        monkeypatch.setitem(__import__("sys").modules, "_startup_err_test_app", mod)
        return app

    @patch(
        "chirp.server.dev.run_dev_server",
        side_effect=OSError(errno.EADDRINUSE, "Address already in use"),
    )
    def test_cli_shows_cli_hint(
        self, mock_dev: MagicMock, fake_app: object, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from chirp.cli import main

        with pytest.raises(SystemExit) as exc_info:
            main(["run", "_startup_err_test_app:app"])

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "chirp run" in captured.err
        assert "--port 8001" in captured.err
        assert "app.run(" not in captured.err

    @patch("chirp.server.dev.run_dev_server", side_effect=RuntimeError("unexpected"))
    def test_cli_unknown_error_re_raises(self, mock_dev: MagicMock, fake_app: object) -> None:
        from chirp.cli import main

        with pytest.raises(RuntimeError, match="unexpected"):
            main(["run", "_startup_err_test_app:app"])

    @patch(
        "chirp.server.dev.run_dev_server",
        side_effect=OSError(errno.EADDRINUSE, "Address already in use"),
    )
    def test_cli_full_traceback_skips_message(
        self,
        mock_dev: MagicMock,
        fake_app: object,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("CHIRP_TRACEBACK", "full")
        from chirp.cli import main

        with pytest.raises(OSError, match="Address already in use"):
            main(["run", "_startup_err_test_app:app"])

        captured = capsys.readouterr()
        assert captured.err == ""
