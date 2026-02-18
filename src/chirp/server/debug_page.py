"""Self-contained debug error page renderer.

Renders rich error pages without depending on kida or any user template
environment. Uses plain f-strings and string concatenation so that a
broken template system cannot prevent error reporting.

The page renders:
- Exception type and message
- Traceback with source context, locals, and app-frame highlighting
- Request context (method, path, headers, query, form, route)
- Template error integration (kida source locations and suggestions)
- Editor-clickable file:line links (via CHIRP_EDITOR env var)

Two output modes:
- Full page: complete HTML document with dark theme
- Fragment: compact HTML snippet for htmx partial responses
"""

import html
import linecache
import os
import sys
import types
from typing import Any

# ---------------------------------------------------------------------------
# Editor link support
# ---------------------------------------------------------------------------

_EDITOR_PRESETS: dict[str, str] = {
    "vscode": "vscode://file/__FILE__:__LINE__",
    "cursor": "cursor://file/__FILE__:__LINE__",
    "sublime": "subl://open?url=file://__FILE__&line=__LINE__",
    "textmate": "txmt://open?url=file://__FILE__&line=__LINE__",
    "idea": "idea://open?file=__FILE__&line=__LINE__",
    "pycharm": "pycharm://open?file=__FILE__&line=__LINE__",
}


def _editor_url(filepath: str, lineno: int) -> str | None:
    """Build a clickable editor URL from CHIRP_EDITOR env var.

    Supports preset names (``vscode``, ``cursor``, ``sublime``, ``textmate``,
    ``idea``, ``pycharm``) or custom patterns with ``__FILE__`` / ``__LINE__``
    placeholders.

    Returns ``None`` if ``CHIRP_EDITOR`` is not set.
    """
    pattern = os.environ.get("CHIRP_EDITOR", "")
    if not pattern:
        return None
    # Resolve presets
    pattern = _EDITOR_PRESETS.get(pattern.lower(), pattern)
    return pattern.replace("__FILE__", filepath).replace("__LINE__", str(lineno))


# ---------------------------------------------------------------------------
# Frame extraction
# ---------------------------------------------------------------------------


def _is_app_frame(filename: str) -> bool:
    """True if the frame is from the application (not stdlib/site-packages)."""
    if "site-packages" in filename:
        return False
    if filename.startswith("<"):
        return False
    # stdlib check — anything inside the Python install
    stdlib_prefix = os.path.dirname(os.__file__)
    return not filename.startswith(stdlib_prefix)


def _extract_frames(
    tb: types.TracebackType | None,
) -> list[dict[str, Any]]:
    """Walk a traceback and extract frame info with source context and locals."""
    frames: list[dict[str, Any]] = []
    while tb is not None:
        frame = tb.tb_frame
        lineno = tb.tb_lineno
        filename = frame.f_code.co_filename
        func_name = frame.f_code.co_name

        # Source context: 5 lines before and after
        source_lines: list[tuple[int, str]] = []
        for i in range(max(1, lineno - 5), lineno + 6):
            line = linecache.getline(filename, i, frame.f_globals)
            if line:
                source_lines.append((i, line.rstrip()))

        # Locals — filter out dunder and overly large values
        local_vars: dict[str, str] = {}
        for name, value in frame.f_locals.items():
            if name.startswith("__") and name.endswith("__"):
                continue
            try:
                r = repr(value)
                if len(r) > 200:
                    r = r[:197] + "..."
                local_vars[name] = r
            except Exception:
                local_vars[name] = "<unrepresentable>"

        frames.append({
            "filename": filename,
            "lineno": lineno,
            "func_name": func_name,
            "source_lines": source_lines,
            "locals": local_vars,
            "is_app": _is_app_frame(filename),
        })
        tb = tb.tb_next

    return frames


# ---------------------------------------------------------------------------
# Kida template error extraction
# ---------------------------------------------------------------------------


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

    ctx: dict[str, Any] = {"type": cls_name}

    # Extract error code and docs URL (available on all Kida exceptions)
    error_code = getattr(exc, "code", None)
    if error_code is not None:
        ctx["error_code"] = getattr(error_code, "value", None)
        ctx["docs_url"] = getattr(error_code, "docs_url", None)

    if cls_name == "TemplateSyntaxError":
        ctx["template"] = getattr(exc, "filename", None) or getattr(exc, "name", None)
        ctx["lineno"] = getattr(exc, "lineno", None)
        ctx["col_offset"] = getattr(exc, "col_offset", None)
        source = getattr(exc, "source", None)
        if source and ctx["lineno"]:
            lines = source.splitlines()
            ln = ctx["lineno"]
            start = max(0, ln - 3)
            end = min(len(lines), ln + 2)
            ctx["source_lines"] = [
                (i + 1, lines[i]) for i in range(start, end)
            ]
        ctx["message"] = getattr(exc, "message", str(exc))
        return ctx

    if cls_name in ("TemplateRuntimeError", "RequiredValueError", "NoneComparisonError"):
        ctx["template"] = getattr(exc, "template_name", None)
        ctx["lineno"] = getattr(exc, "lineno", None)
        ctx["expression"] = getattr(exc, "expression", None)
        ctx["values"] = getattr(exc, "values", {})
        ctx["suggestion"] = getattr(exc, "suggestion", None)
        ctx["message"] = getattr(exc, "message", str(exc))
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
        ctx["message"] = str(exc)
        # Extract source snippet (new: UndefinedError now has source context)
        snippet = getattr(exc, "source_snippet", None)
        if snippet is not None:
            ctx["source_lines"] = list(getattr(snippet, "lines", ()))
            ctx["snippet_error_line"] = getattr(snippet, "error_line", None)
        return ctx

    if cls_name == "TemplateNotFoundError":
        ctx["message"] = str(exc)
        return ctx

    return None


# ---------------------------------------------------------------------------
# Request context extraction
# ---------------------------------------------------------------------------

# Headers whose values should be masked in debug output
_SENSITIVE_HEADERS = frozenset({
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-auth-token",
    "proxy-authorization",
})


def _extract_request_context(request: Any) -> dict[str, Any]:
    """Extract displayable request context from a chirp Request."""
    ctx: dict[str, Any] = {
        "method": getattr(request, "method", "?"),
        "path": getattr(request, "path", "?"),
        "http_version": getattr(request, "http_version", "?"),
    }

    # Headers with sensitive value masking
    headers = getattr(request, "headers", None)
    if headers:
        masked: list[tuple[str, str]] = []
        # Headers may be a Headers object or dict-like
        items = headers.items() if hasattr(headers, "items") else []
        for name, value in items:
            name_lower = name.lower() if isinstance(name, str) else name
            if name_lower in _SENSITIVE_HEADERS:
                masked.append((str(name), "••••••••"))
            else:
                masked.append((str(name), str(value)))
        ctx["headers"] = masked

    # Query parameters
    query = getattr(request, "query", None)
    if query:
        items = query.items() if hasattr(query, "items") else []
        ctx["query"] = [(str(k), str(v)) for k, v in items]

    # Path params (from route match)
    path_params = getattr(request, "path_params", None)
    if path_params:
        ctx["path_params"] = dict(path_params)

    # Client address
    client = getattr(request, "client", None)
    if client:
        ctx["client"] = f"{client[0]}:{client[1]}"

    return ctx


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = """\
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: ui-monospace, 'Cascadia Code', 'Source Code Pro', Menlo, Consolas,
                 'DejaVu Sans Mono', monospace;
    background: #1a1b26; color: #a9b1d6; line-height: 1.6;
    padding: 2rem; font-size: 14px;
}
.error-page { max-width: 960px; margin: 0 auto; }
h1 { color: #f7768e; font-size: 1.4rem; margin-bottom: 0.5rem; }
h2 { color: #7aa2f7; font-size: 1.1rem; margin: 1.5rem 0 0.5rem; border-bottom: 1px solid #2f3549; padding-bottom: 0.3rem; }
h3 { color: #bb9af7; font-size: 0.95rem; margin: 0.8rem 0 0.3rem; }
.exc-message { color: #e0af68; font-size: 1rem; margin-bottom: 1rem; white-space: pre-wrap; word-break: break-word; }
.exc-chain { color: #565f89; font-size: 0.85rem; margin-bottom: 0.5rem; font-style: italic; }

/* Frames */
.frame { margin: 0.5rem 0; border: 1px solid #2f3549; border-radius: 6px; overflow: hidden; }
.frame.app-frame { border-color: #7aa2f7; }
.frame-header { padding: 0.4rem 0.8rem; background: #24283b; font-size: 0.85rem; display: flex; justify-content: space-between; align-items: center; }
.frame-header a { color: #7dcfff; text-decoration: none; }
.frame-header a:hover { text-decoration: underline; }
.frame-header .func { color: #bb9af7; }
.frame-header .app-badge { color: #9ece6a; font-size: 0.75rem; margin-left: 0.5rem; }
.source { padding: 0; margin: 0; overflow-x: auto; }
.source-line { display: flex; padding: 0 0.8rem; font-size: 0.82rem; }
.source-line .lineno { color: #565f89; min-width: 3.5rem; text-align: right; padding-right: 1rem; user-select: none; flex-shrink: 0; }
.source-line .code { white-space: pre; }
.source-line.error-line { background: rgba(247, 118, 142, 0.15); }
.source-line.error-line .lineno { color: #f7768e; }

/* Locals */
.locals-toggle { cursor: pointer; color: #565f89; font-size: 0.8rem; padding: 0.3rem 0.8rem; user-select: none; }
.locals-toggle:hover { color: #7aa2f7; }
.locals { display: none; padding: 0.4rem 0.8rem; background: #1a1b26; border-top: 1px solid #2f3549; font-size: 0.8rem; }
.locals.open { display: block; }
.local-var { display: flex; gap: 0.5rem; padding: 0.15rem 0; }
.local-var .name { color: #7dcfff; min-width: 120px; flex-shrink: 0; }
.local-var .value { color: #a9b1d6; white-space: pre-wrap; word-break: break-all; }

/* Request context */
.request-panel { background: #24283b; border-radius: 6px; padding: 0.8rem; margin: 0.5rem 0; }
.request-line { display: flex; gap: 0.5rem; padding: 0.15rem 0; font-size: 0.85rem; }
.request-line .label { color: #7aa2f7; min-width: 140px; flex-shrink: 0; }
.request-line .val { color: #a9b1d6; word-break: break-all; }

/* Template error panel */
.template-panel { background: #1f2335; border: 1px solid #e0af68; border-radius: 6px; padding: 0.8rem; margin: 0.5rem 0; }
.template-panel h3 { color: #e0af68; }
.template-source { margin: 0.5rem 0; }
.template-source .source-line { font-size: 0.85rem; }
.template-suggestion { color: #9ece6a; font-style: italic; margin-top: 0.4rem; }
.template-values { margin-top: 0.4rem; }

/* Fragment (compact) mode */
.chirp-error-fragment { font-family: ui-monospace, monospace; font-size: 13px; color: #a9b1d6; background: #1a1b26; padding: 1rem; border: 2px solid #f7768e; border-radius: 6px; max-height: 70vh; overflow-y: auto; }
.chirp-error-fragment h1 { font-size: 1.1rem; }
.chirp-error-fragment .frame { margin: 0.3rem 0; }
"""

_TOGGLE_JS = """\
document.querySelectorAll('.locals-toggle').forEach(el => {
    el.addEventListener('click', () => {
        const panel = el.nextElementSibling;
        panel.classList.toggle('open');
        el.textContent = panel.classList.contains('open') ? '▾ locals' : '▸ locals';
    });
});
"""


# ---------------------------------------------------------------------------
# HTML builders
# ---------------------------------------------------------------------------


def _esc(text: str) -> str:
    """HTML-escape a string."""
    return html.escape(str(text), quote=True)


def _render_source_lines(
    source_lines: list[tuple[int, str]],
    error_lineno: int,
) -> str:
    """Render source lines with error highlighting."""
    parts: list[str] = []
    for lineno, code in source_lines:
        cls = " error-line" if lineno == error_lineno else ""
        parts.append(
            f'<div class="source-line{cls}">'
            f'<span class="lineno">{lineno}</span>'
            f'<span class="code">{_esc(code)}</span>'
            f"</div>"
        )
    return "".join(parts)


def _render_locals(local_vars: dict[str, str]) -> str:
    """Render local variables panel."""
    if not local_vars:
        return ""
    items = "".join(
        f'<div class="local-var">'
        f'<span class="name">{_esc(name)}</span>'
        f'<span class="value">{_esc(value)}</span>'
        f"</div>"
        for name, value in local_vars.items()
    )
    return (
        f'<div class="locals-toggle">▸ locals</div>'
        f'<div class="locals">{items}</div>'
    )


def _render_frame(frame: dict[str, Any]) -> str:
    """Render a single traceback frame."""
    filename = frame["filename"]
    lineno = frame["lineno"]
    func_name = frame["func_name"]
    is_app = frame["is_app"]

    # File path — possibly clickable
    editor_link = _editor_url(filename, lineno)
    location = f"{_esc(filename)}:{lineno}"
    if editor_link:
        location = f'<a href="{_esc(editor_link)}">{location}</a>'

    app_badge = ' <span class="app-badge">APP</span>' if is_app else ""
    frame_cls = "frame app-frame" if is_app else "frame"

    source_html = _render_source_lines(frame["source_lines"], lineno)
    locals_html = _render_locals(frame["locals"])

    return (
        f'<div class="{frame_cls}">'
        f'<div class="frame-header">'
        f"<span>{location}</span>"
        f'<span><span class="func">{_esc(func_name)}</span>{app_badge}</span>'
        f"</div>"
        f'<div class="source">{source_html}</div>'
        f"{locals_html}"
        f"</div>"
    )


def _render_template_panel(ctx: dict[str, Any]) -> str:
    """Render the kida template error panel."""
    parts: list[str] = []
    parts.append('<div class="template-panel">')

    # Error code badge + type header
    error_code = ctx.get("error_code")
    if error_code:
        parts.append(
            f'<h3><span style="background:#f7768e;color:#1a1b26;padding:2px 8px;'
            f'border-radius:3px;font-size:0.85em;margin-right:8px">{_esc(error_code)}</span>'
            f'Template Error: {_esc(ctx["type"])}</h3>'
        )
    else:
        parts.append(f'<h3>Template Error: {_esc(ctx["type"])}</h3>')

    message = ctx.get("message", "")
    parts.append(f'<div class="exc-message">{_esc(message)}</div>')

    # Location info
    template = ctx.get("template")
    lineno = ctx.get("lineno")
    if template or lineno:
        loc = _esc(str(template or "<template>"))
        if lineno:
            loc += f":{lineno}"
        parts.append(f'<div class="request-line"><span class="label">Template</span><span class="val">{loc}</span></div>')

    # Expression
    expression = ctx.get("expression")
    if expression:
        parts.append(f'<div class="request-line"><span class="label">Expression</span><span class="val">{_esc(expression)}</span></div>')

    # Source lines (syntax errors have lineno as highlight, runtime/undefined use snippet_error_line)
    source_lines = ctx.get("source_lines")
    highlight_line = ctx.get("snippet_error_line") or lineno
    if source_lines and highlight_line:
        parts.append(f'<div class="template-source">{_render_source_lines(source_lines, highlight_line)}</div>')

    # Values (for runtime errors)
    values = ctx.get("values", {})
    if values:
        parts.append('<div class="template-values"><strong>Values:</strong>')
        for name, value in values.items():
            type_name = type(value).__name__
            value_repr = repr(value)
            if len(value_repr) > 80:
                value_repr = value_repr[:77] + "..."
            parts.append(f'<div class="local-var"><span class="name">{_esc(name)}</span><span class="value">{_esc(value_repr)} ({_esc(type_name)})</span></div>')
        parts.append("</div>")

    # Variable name (for undefined errors)
    variable = ctx.get("variable")
    if variable:
        parts.append(f'<div class="request-line"><span class="label">Variable</span><span class="val">{_esc(variable)}</span></div>')

    # Suggestion
    suggestion = ctx.get("suggestion")
    if suggestion:
        parts.append(f'<div class="template-suggestion">💡 {_esc(suggestion)}</div>')

    # Docs link
    docs_url = ctx.get("docs_url")
    if docs_url and error_code:
        parts.append(
            f'<div class="template-suggestion" style="margin-top:8px">'
            f'📖 <a href="{_esc(docs_url)}" style="color:#7aa2f7">'
            f'{_esc(error_code)} documentation</a></div>'
        )

    parts.append("</div>")
    return "".join(parts)


def _render_request_panel(request: Any) -> str:
    """Render request context panel."""
    ctx = _extract_request_context(request)
    parts: list[str] = []
    parts.append('<div class="request-panel">')

    # Method + path
    method = ctx["method"]
    path = ctx["path"]
    version = ctx["http_version"]
    parts.append(f'<div class="request-line"><span class="label">Request</span><span class="val">{_esc(method)} {_esc(path)} HTTP/{_esc(version)}</span></div>')

    # Client
    client = ctx.get("client")
    if client:
        parts.append(f'<div class="request-line"><span class="label">Client</span><span class="val">{_esc(client)}</span></div>')

    # Path params
    path_params = ctx.get("path_params")
    if path_params:
        pp = ", ".join(f"{k}={v!r}" for k, v in path_params.items())
        parts.append(f'<div class="request-line"><span class="label">Path Params</span><span class="val">{_esc(pp)}</span></div>')

    # Query params
    query = ctx.get("query")
    if query:
        parts.append('<div class="request-line"><span class="label">Query</span><span class="val">')
        for k, v in query:
            parts.append(f"{_esc(k)}={_esc(v)} ")
        parts.append("</span></div>")

    # Headers
    headers = ctx.get("headers", [])
    if headers:
        parts.append('<div class="request-line"><span class="label">Headers</span><span class="val">')
        for name, value in headers:
            parts.append(f"{_esc(name)}: {_esc(value)}<br>")
        parts.append("</span></div>")

    parts.append("</div>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_debug_page(
    exc: BaseException,
    request: Any,
    *,
    is_fragment: bool = False,
) -> str:
    """Render a rich debug error page.

    Args:
        exc: The exception that caused the error.
        request: The chirp Request object.
        is_fragment: If True, render a compact fragment instead of a full page.

    Returns:
        HTML string — either a full page or a fragment snippet.

    """
    exc_type = type(exc).__name__
    exc_module = type(exc).__module__ or ""
    qualified = f"{exc_module}.{exc_type}" if exc_module and exc_module != "builtins" else exc_type
    exc_message = str(exc)

    # Extract traceback frames
    tb = exc.__traceback__
    frames = _extract_frames(tb)

    # Check for chained exceptions
    cause = exc.__cause__
    context = exc.__context__ if not exc.__suppress_context__ else None
    chain_note = ""
    if cause:
        chain_note = f"The above exception was the direct cause (raised from {type(cause).__name__})"
    elif context:
        chain_note = f"During handling, another exception occurred ({type(context).__name__})"

    # Kida template error context
    template_ctx = _extract_template_context(exc)
    # Also check __cause__ for wrapped template errors
    if template_ctx is None and cause:
        template_ctx = _extract_template_context(cause)
    if template_ctx is None and context:
        template_ctx = _extract_template_context(context)

    # Build content sections
    sections: list[str] = []

    # Exception header
    sections.append(f"<h1>{_esc(qualified)}</h1>")
    sections.append(f'<div class="exc-message">{_esc(exc_message)}</div>')
    if chain_note:
        sections.append(f'<div class="exc-chain">{_esc(chain_note)}</div>')

    # Template error panel (before traceback for prominence)
    if template_ctx:
        sections.append(_render_template_panel(template_ctx))

    # Traceback
    if frames:
        sections.append("<h2>Traceback</h2>")
        sections.extend(_render_frame(f) for f in frames)

    # Request context
    sections.append("<h2>Request</h2>")
    sections.append(_render_request_panel(request))

    # Python / chirp info
    sections.append("<h2>Environment</h2>")
    sections.append('<div class="request-panel">')
    sections.append(f'<div class="request-line"><span class="label">Python</span><span class="val">{_esc(sys.version)}</span></div>')

    try:
        import chirp

        chirp_version = getattr(chirp, "__version__", "unknown")
    except Exception:
        chirp_version = "unknown"
    sections.append(f'<div class="request-line"><span class="label">Chirp</span><span class="val">{_esc(chirp_version)}</span></div>')
    sections.append("</div>")

    body_html = "\n".join(sections)

    if is_fragment:
        return (
            f'<div class="chirp-error chirp-error-fragment" data-status="500">'
            f"<style>{_CSS}</style>"
            f"{body_html}"
            f"<script>{_TOGGLE_JS}</script>"
            f"</div>"
        )

    return (
        f"<!DOCTYPE html>"
        f'<html lang="en"><head>'
        f"<meta charset=\"utf-8\">"
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_esc(qualified)}: {_esc(exc_message[:80])}</title>"
        f"<style>{_CSS}</style>"
        f"</head><body>"
        f'<div class="error-page">{body_html}</div>'
        f"<script>{_TOGGLE_JS}</script>"
        f"</body></html>"
    )
