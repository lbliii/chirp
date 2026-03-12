"""Kida template error context extraction for debug page."""

from typing import Any


def _extract_template_context(exc: BaseException) -> dict[str, Any] | None:
    """Extract rich context from kida template exceptions.

    Returns a dict with template-specific error info, or None if
    the exception is not a kida template error.
    """
    cls_name = type(exc).__name__
    module = type(exc).__module__ or ""

    # Only handle kida exceptions
    if "kida" not in module:
        return None

    from chirp.server.terminal_errors import _plain_error_message

    ctx: dict[str, Any] = {"type": cls_name}

    # Extract error code and docs URL (available on all Kida exceptions)
    error_code = getattr(exc, "code", None)
    if error_code is not None:
        ctx["error_code"] = getattr(error_code, "value", None)
        ctx["docs_url"] = getattr(error_code, "docs_url", None)

    if cls_name in ("TemplateSyntaxError", "ParseError"):
        ctx["template"] = getattr(exc, "filename", None) or getattr(exc, "name", None)
        ctx["lineno"] = getattr(exc, "lineno", None)
        ctx["col_offset"] = getattr(exc, "col_offset", None)
        ctx["suggestion"] = getattr(exc, "suggestion", None)
        source = getattr(exc, "source", None)
        if source and ctx["lineno"]:
            lines = source.splitlines()
            ln = ctx["lineno"]
            start = max(0, ln - 3)
            end = min(len(lines), ln + 2)
            ctx["source_lines"] = [(i + 1, lines[i]) for i in range(start, end)]
        ctx["message"] = _plain_error_message(exc)
        return ctx

    if cls_name in ("TemplateRuntimeError", "RequiredValueError", "NoneComparisonError"):
        ctx["template"] = getattr(exc, "template_name", None)
        ctx["lineno"] = getattr(exc, "lineno", None)
        ctx["expression"] = getattr(exc, "expression", None)
        ctx["values"] = getattr(exc, "values", {})
        ctx["suggestion"] = getattr(exc, "suggestion", None)
        ctx["message"] = _plain_error_message(exc)
        # Extract source snippet (new: runtime errors now have source context)
        snippet = getattr(exc, "source_snippet", None)
        if snippet is not None:
            ctx["source_lines"] = list(getattr(snippet, "lines", ()))
            ctx["snippet_error_line"] = getattr(snippet, "error_line", None)
        return ctx

    if cls_name == "UndefinedError":
        ctx["template"] = getattr(exc, "template", None)
        ctx["lineno"] = getattr(exc, "lineno", None)
        ctx["variable"] = getattr(exc, "name", None)
        ctx["message"] = _plain_error_message(exc)
        # Extract source snippet (new: UndefinedError now has source context)
        snippet = getattr(exc, "source_snippet", None)
        if snippet is not None:
            ctx["source_lines"] = list(getattr(snippet, "lines", ()))
            ctx["snippet_error_line"] = getattr(snippet, "error_line", None)
        return ctx

    if cls_name == "TemplateNotFoundError":
        ctx["message"] = _plain_error_message(exc)
        return ctx

    return None
