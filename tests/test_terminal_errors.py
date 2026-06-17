"""Tests for chirp.server.terminal_errors (runtime / template logging)."""

import errno

import pytest

from chirp.server.terminal_errors import format_template_error, is_client_disconnect


class TestFormatTemplateError:
    """format_template_error must not embed ANSI (JSON logs, plain terminals)."""

    def test_strips_ansi_from_kida_format_compact(self) -> None:
        class FakeKidaError(Exception):
            __module__ = "kida.errors.runtime"

            def format_compact(self) -> str:
                return "\033[91m\033[1mK-RUN-001\033[0m: boom"

        exc = FakeKidaError()
        out = format_template_error(exc)
        assert "\033" not in out
        assert "\x1b" not in out
        assert "K-RUN-001" in out
        assert "boom" in out
        assert "Template Error" in out


class TestIsClientDisconnect:
    """is_client_disconnect classifies benign client-gone errors for streaming/SSE."""

    @pytest.mark.issue(355)
    @pytest.mark.parametrize(
        "exc",
        [
            ConnectionResetError(errno.ECONNRESET, "reset by peer"),
            BrokenPipeError(errno.EPIPE, "broken pipe"),
            ConnectionAbortedError(),
            OSError(errno.ECONNRESET, "reset"),
            OSError(errno.EPIPE, "pipe"),
            OSError(errno.ECONNABORTED, "aborted"),
        ],
    )
    def test_disconnect_classes_are_benign(self, exc: BaseException) -> None:
        assert is_client_disconnect(exc) is True

    @pytest.mark.issue(355)
    @pytest.mark.parametrize(
        "exc",
        [
            RuntimeError("generator misuse"),
            ValueError("bad value"),
            OSError(errno.ENOENT, "missing file"),  # an OSError, but not a disconnect
            KeyError("missing"),
            # ConnectionRefusedError is ECONNREFUSED — an *outbound* failure (the
            # generator's own upstream refused), a genuine server error the
            # classifier must NOT swallow as a client disconnect.
            ConnectionRefusedError(errno.ECONNREFUSED, "refused"),
            ConnectionError("ambiguous peer-gone with no errno"),
        ],
    )
    def test_genuine_errors_are_not_disconnects(self, exc: BaseException) -> None:
        assert is_client_disconnect(exc) is False
