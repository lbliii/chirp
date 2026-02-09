"""Tests for the self-contained debug error page renderer.

Covers frame extraction, template error integration, request context
masking, editor URL generation, and both full-page and fragment output.
"""

import os
import types

import pytest

from chirp.server.debug_page import (
    _editor_url,
    _extract_frames,
    _extract_request_context,
    _extract_template_context,
    _is_app_frame,
    render_debug_page,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(
    *,
    method: str = "GET",
    path: str = "/test",
    http_version: str = "1.1",
    headers: object | None = None,
    query: object | None = None,
    path_params: dict[str, str] | None = None,
    client: tuple[str, int] | None = ("127.0.0.1", 5000),
) -> object:
    """Build a lightweight request-like object for testing."""

    class FakeHeaders:
        def __init__(self, pairs: list[tuple[str, str]]) -> None:
            self._pairs = pairs

        def items(self):
            return iter(self._pairs)

    class FakeQuery:
        def __init__(self, pairs: list[tuple[str, str]]) -> None:
            self._pairs = pairs

        def items(self):
            return iter(self._pairs)

    class FakeRequest:
        pass

    req = FakeRequest()
    req.method = method  # type: ignore[attr-defined]
    req.path = path  # type: ignore[attr-defined]
    req.http_version = http_version  # type: ignore[attr-defined]
    req.headers = FakeHeaders(headers or [])  # type: ignore[attr-defined]
    req.query = FakeQuery(query or [])  # type: ignore[attr-defined]
    req.path_params = path_params or {}  # type: ignore[attr-defined]
    req.client = client  # type: ignore[attr-defined]
    return req


def _raise_and_capture() -> tuple[Exception, types.TracebackType]:
    """Raise a RuntimeError and capture its traceback."""
    try:
        msg = "test error"
        raise RuntimeError(msg)
    except RuntimeError as exc:
        return exc, exc.__traceback__  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# _is_app_frame
# ---------------------------------------------------------------------------


class TestIsAppFrame:
    """Application vs framework/stdlib frame classification."""

    def test_site_packages_is_not_app(self) -> None:
        assert _is_app_frame("/venv/lib/python3.14/site-packages/chirp/app.py") is False

    def test_stdlib_is_not_app(self) -> None:
        import os as os_mod

        stdlib_path = os.path.join(os.path.dirname(os_mod.__file__), "json/__init__.py")
        assert _is_app_frame(stdlib_path) is False

    def test_angle_bracket_is_not_app(self) -> None:
        assert _is_app_frame("<frozen importlib._bootstrap>") is False

    def test_user_code_is_app(self) -> None:
        assert _is_app_frame("/home/user/myproject/app.py") is True

    def test_cwd_file_is_app(self) -> None:
        assert _is_app_frame("./routes/index.py") is True


# ---------------------------------------------------------------------------
# _extract_frames
# ---------------------------------------------------------------------------


class TestExtractFrames:
    """Traceback frame extraction with source and locals."""

    def test_extracts_at_least_one_frame(self) -> None:
        exc, tb = _raise_and_capture()
        frames = _extract_frames(tb)
        assert len(frames) >= 1

    def test_frame_has_required_keys(self) -> None:
        exc, tb = _raise_and_capture()
        frames = _extract_frames(tb)
        frame = frames[-1]
        assert "filename" in frame
        assert "lineno" in frame
        assert "func_name" in frame
        assert "source_lines" in frame
        assert "locals" in frame
        assert "is_app" in frame

    def test_frame_filename_matches_this_file(self) -> None:
        exc, tb = _raise_and_capture()
        frames = _extract_frames(tb)
        assert any("test_debug_page" in f["filename"] for f in frames)

    def test_frame_has_source_context(self) -> None:
        exc, tb = _raise_and_capture()
        frames = _extract_frames(tb)
        frame = frames[-1]
        assert len(frame["source_lines"]) > 0
        # Source lines are (lineno, code) tuples
        lineno, code = frame["source_lines"][0]
        assert isinstance(lineno, int)
        assert isinstance(code, str)

    def test_dunder_locals_are_filtered(self) -> None:
        exc, tb = _raise_and_capture()
        frames = _extract_frames(tb)
        frame = frames[-1]
        for name in frame["locals"]:
            assert not (name.startswith("__") and name.endswith("__"))

    def test_none_traceback_returns_empty(self) -> None:
        assert _extract_frames(None) == []


# ---------------------------------------------------------------------------
# _extract_template_context
# ---------------------------------------------------------------------------


class TestExtractTemplateContext:
    """Kida template error context extraction."""

    def test_non_kida_exception_returns_none(self) -> None:
        assert _extract_template_context(RuntimeError("oops")) is None

    def test_template_syntax_error(self) -> None:
        from kida.environment.exceptions import TemplateSyntaxError

        exc = TemplateSyntaxError(
            "Unexpected token",
            lineno=5,
            name="index.html",
            source="{% block %}\n{{ title }}\n{% endblock %}\n{{ bad }\n{% end %}",
            col_offset=7,
        )
        ctx = _extract_template_context(exc)
        assert ctx is not None
        assert ctx["type"] == "TemplateSyntaxError"
        assert ctx["lineno"] == 5
        assert "Unexpected token" in ctx["message"]

    def test_template_runtime_error(self) -> None:
        from kida.environment.exceptions import TemplateRuntimeError

        exc = TemplateRuntimeError(
            "'NoneType' has no attribute 'title'",
            expression="{{ post.title }}",
            values={"post": None},
            template_name="article.html",
            lineno=15,
            suggestion="Use {{ post.title | default('') }}",
        )
        ctx = _extract_template_context(exc)
        assert ctx is not None
        assert ctx["type"] == "TemplateRuntimeError"
        assert ctx["template"] == "article.html"
        assert ctx["lineno"] == 15
        assert ctx["expression"] == "{{ post.title }}"
        assert ctx["suggestion"] is not None

    def test_undefined_error(self) -> None:
        from kida.environment.exceptions import UndefinedError

        exc = UndefinedError("titl", template="page.html", lineno=3)
        ctx = _extract_template_context(exc)
        assert ctx is not None
        assert ctx["type"] == "UndefinedError"
        assert ctx["variable"] == "titl"
        assert ctx["template"] == "page.html"

    def test_template_not_found_error(self) -> None:
        from kida.environment.exceptions import TemplateNotFoundError

        exc = TemplateNotFoundError("missing.html")
        ctx = _extract_template_context(exc)
        assert ctx is not None
        assert ctx["type"] == "TemplateNotFoundError"


# ---------------------------------------------------------------------------
# _extract_request_context
# ---------------------------------------------------------------------------


class TestExtractRequestContext:
    """Request context extraction with header masking."""

    def test_basic_request_context(self) -> None:
        req = _make_request(method="POST", path="/api/items")
        ctx = _extract_request_context(req)
        assert ctx["method"] == "POST"
        assert ctx["path"] == "/api/items"

    def test_sensitive_headers_masked(self) -> None:
        req = _make_request(headers=[
            ("content-type", "text/html"),
            ("authorization", "Bearer secret-token"),
            ("cookie", "session=abc123"),
            ("x-api-key", "my-key"),
        ])
        ctx = _extract_request_context(req)
        header_dict = dict(ctx["headers"])
        assert header_dict["content-type"] == "text/html"
        assert header_dict["authorization"] == "••••••••"
        assert header_dict["cookie"] == "••••••••"
        assert header_dict["x-api-key"] == "••••••••"

    def test_query_params(self) -> None:
        req = _make_request(query=[("page", "2"), ("sort", "name")])
        ctx = _extract_request_context(req)
        assert ("page", "2") in ctx["query"]

    def test_path_params(self) -> None:
        req = _make_request(path_params={"id": "42"})
        ctx = _extract_request_context(req)
        assert ctx["path_params"]["id"] == "42"

    def test_client_address(self) -> None:
        req = _make_request(client=("10.0.0.1", 9999))
        ctx = _extract_request_context(req)
        assert ctx["client"] == "10.0.0.1:9999"


# ---------------------------------------------------------------------------
# _editor_url
# ---------------------------------------------------------------------------


class TestEditorUrl:
    """Editor URL generation from CHIRP_EDITOR env var."""

    def test_no_env_var_returns_none(self, monkeypatch) -> None:
        monkeypatch.delenv("CHIRP_EDITOR", raising=False)
        assert _editor_url("/app.py", 42) is None

    def test_vscode_preset(self, monkeypatch) -> None:
        monkeypatch.setenv("CHIRP_EDITOR", "vscode")
        url = _editor_url("/app.py", 42)
        assert url == "vscode://file//app.py:42"

    def test_cursor_preset(self, monkeypatch) -> None:
        monkeypatch.setenv("CHIRP_EDITOR", "cursor")
        url = _editor_url("/app.py", 10)
        assert url == "cursor://file//app.py:10"

    def test_pycharm_preset(self, monkeypatch) -> None:
        monkeypatch.setenv("CHIRP_EDITOR", "pycharm")
        url = _editor_url("/app.py", 5)
        assert url == "pycharm://open?file=/app.py&line=5"

    def test_custom_pattern(self, monkeypatch) -> None:
        monkeypatch.setenv("CHIRP_EDITOR", "myeditor://open?f=__FILE__&l=__LINE__")
        url = _editor_url("/code/app.py", 99)
        assert url == "myeditor://open?f=/code/app.py&l=99"

    def test_preset_case_insensitive(self, monkeypatch) -> None:
        monkeypatch.setenv("CHIRP_EDITOR", "VSCode")
        url = _editor_url("/app.py", 1)
        assert url is not None
        assert url.startswith("vscode://")


# ---------------------------------------------------------------------------
# render_debug_page — full page
# ---------------------------------------------------------------------------


class TestRenderDebugPageFull:
    """Full-page debug error rendering."""

    def test_contains_exception_type(self) -> None:
        exc, _ = _raise_and_capture()
        html = render_debug_page(exc, _make_request())
        assert "RuntimeError" in html

    def test_contains_exception_message(self) -> None:
        exc, _ = _raise_and_capture()
        html = render_debug_page(exc, _make_request())
        assert "test error" in html

    def test_is_full_html_document(self) -> None:
        exc, _ = _raise_and_capture()
        html = render_debug_page(exc, _make_request())
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html
        assert "<style>" in html

    def test_contains_error_page_class(self) -> None:
        exc, _ = _raise_and_capture()
        html = render_debug_page(exc, _make_request())
        assert 'class="error-page"' in html

    def test_contains_request_context(self) -> None:
        exc, _ = _raise_and_capture()
        html = render_debug_page(exc, _make_request(method="POST", path="/boom"))
        assert "POST" in html
        assert "/boom" in html

    def test_contains_traceback_section(self) -> None:
        exc, _ = _raise_and_capture()
        html = render_debug_page(exc, _make_request())
        assert "Traceback" in html

    def test_contains_source_lines(self) -> None:
        exc, _ = _raise_and_capture()
        html = render_debug_page(exc, _make_request())
        # Should contain at least one source-line div
        assert 'class="source-line' in html

    def test_no_chirp_error_fragment_wrapper(self) -> None:
        """Full page should NOT use the chirp-error-fragment div wrapper."""
        exc, _ = _raise_and_capture()
        html = render_debug_page(exc, _make_request())
        # The CSS class name appears in the stylesheet, but the wrapper div should not
        assert 'class="chirp-error chirp-error-fragment"' not in html

    def test_editor_links_when_env_set(self, monkeypatch) -> None:
        monkeypatch.setenv("CHIRP_EDITOR", "vscode")
        exc, _ = _raise_and_capture()
        html = render_debug_page(exc, _make_request())
        assert "vscode://file/" in html

    def test_no_editor_links_by_default(self, monkeypatch) -> None:
        monkeypatch.delenv("CHIRP_EDITOR", raising=False)
        exc, _ = _raise_and_capture()
        html = render_debug_page(exc, _make_request())
        assert "vscode://file/" not in html


# ---------------------------------------------------------------------------
# render_debug_page — fragment
# ---------------------------------------------------------------------------


class TestRenderDebugPageFragment:
    """Fragment (compact) debug error rendering for htmx."""

    def test_is_not_full_html_document(self) -> None:
        exc, _ = _raise_and_capture()
        html = render_debug_page(exc, _make_request(), is_fragment=True)
        assert "<!DOCTYPE html>" not in html
        assert "</html>" not in html

    def test_has_chirp_error_class(self) -> None:
        exc, _ = _raise_and_capture()
        html = render_debug_page(exc, _make_request(), is_fragment=True)
        assert 'chirp-error' in html
        assert 'chirp-error-fragment' in html

    def test_has_data_status(self) -> None:
        exc, _ = _raise_and_capture()
        html = render_debug_page(exc, _make_request(), is_fragment=True)
        assert 'data-status="500"' in html

    def test_contains_exception_info(self) -> None:
        exc, _ = _raise_and_capture()
        html = render_debug_page(exc, _make_request(), is_fragment=True)
        assert "RuntimeError" in html
        assert "test error" in html

    def test_contains_traceback(self) -> None:
        exc, _ = _raise_and_capture()
        html = render_debug_page(exc, _make_request(), is_fragment=True)
        assert "Traceback" in html


# ---------------------------------------------------------------------------
# Template error rendering
# ---------------------------------------------------------------------------


class TestRenderDebugPageTemplateErrors:
    """Debug page renders kida template errors with rich context."""

    def test_syntax_error_shows_template_panel(self) -> None:
        from kida.environment.exceptions import TemplateSyntaxError

        exc = TemplateSyntaxError("Unexpected end tag", lineno=3, name="layout.html")
        html = render_debug_page(exc, _make_request())
        assert "Template Error" in html
        assert "TemplateSyntaxError" in html
        assert "Unexpected end tag" in html

    def test_undefined_error_shows_variable(self) -> None:
        from kida.environment.exceptions import UndefinedError

        exc = UndefinedError("titl", template="page.html", lineno=5)
        html = render_debug_page(exc, _make_request())
        assert "Template Error" in html
        assert "UndefinedError" in html

    def test_runtime_error_shows_suggestion(self) -> None:
        from kida.environment.exceptions import TemplateRuntimeError

        exc = TemplateRuntimeError(
            "NoneType error",
            suggestion="Use | default('')",
            template_name="post.html",
        )
        html = render_debug_page(exc, _make_request())
        assert "Use | default(&#x27;&#x27;)" in html or "default(&#39;&#39;)" in html or "default(" in html


# ---------------------------------------------------------------------------
# Chained exceptions
# ---------------------------------------------------------------------------


class TestRenderDebugPageChainedExceptions:
    """Debug page handles exception chaining."""

    def test_cause_noted(self) -> None:
        try:
            try:
                msg = "original"
                raise ValueError(msg)
            except ValueError as original:
                msg2 = "wrapper"
                raise RuntimeError(msg2) from original
        except RuntimeError as exc:
            html = render_debug_page(exc, _make_request())
            assert "direct cause" in html

    def test_context_noted(self) -> None:
        try:
            try:
                msg = "first"
                raise ValueError(msg)
            except ValueError:
                msg2 = "second"
                raise RuntimeError(msg2)  # noqa: B904
        except RuntimeError as exc:
            html = render_debug_page(exc, _make_request())
            assert "another exception occurred" in html
