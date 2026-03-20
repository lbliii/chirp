"""Tests for chirp.server.terminal_errors (runtime / template logging)."""

from chirp.server.terminal_errors import format_template_error


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
