"""HTML builders and render_debug_page assembly."""

import html
import sys
from typing import Any

from chirp.server.debug.editor import _editor_url
from chirp.server.debug.frames import _collapse_framework_frames, _extract_frames
from chirp.server.debug.render_plan_snapshot import read_render_debug_from_request
from chirp.server.debug.request_context import _extract_request_context
from chirp.server.debug.styles import _CSS, _TOGGLE_JS
from chirp.server.debug.template_context import _extract_template_context


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
    return f'<div class="locals-toggle">▸ locals</div><div class="locals">{items}</div>'


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


def _render_collapsed_frames(group: dict[str, Any]) -> str:
    """Render a collapsed group of framework frames with expand toggle."""
    summary = group["summary"]
    frames = group["frames"]
    frames_html = "".join(_render_frame(f) for f in frames)
    return (
        f'<div class="frame-collapsed">'
        f'<div class="collapse-toggle">'
        f'<span class="arrow">▸</span>{_esc(summary)} (click to expand)'
        f"</div>"
        f'<div class="collapse-content">{frames_html}</div>'
        f"</div>"
    )


def _render_template_panel(ctx: dict[str, Any]) -> str:
    """Render the kida template error panel."""
    parts: list[str] = []
    parts.append('<div class="template-panel">')

    # Error code badge + type header (Kida branding for AI consumers)
    error_code = ctx.get("error_code")
    if error_code:
        parts.append(
            f'<h3><span style="background:#f7768e;color:#1a1b26;padding:2px 8px;'
            f'border-radius:3px;font-size:0.85em;margin-right:8px">{_esc(error_code)}</span>'
            f"Kida Template Error: {_esc(ctx['type'])}</h3>"
        )
    else:
        parts.append(f"<h3>Kida Template Error: {_esc(ctx['type'])}</h3>")

    message = ctx.get("message", "")
    parts.append(f'<div class="exc-message">{_esc(message)}</div>')

    # Location info
    template = ctx.get("template")
    lineno = ctx.get("lineno")
    if template or lineno:
        loc = _esc(str(template or "<template>"))
        if lineno:
            loc += f":{lineno}"
        parts.append(
            f'<div class="request-line"><span class="label">Template</span><span class="val">{loc}</span></div>'
        )

    # Expression
    expression = ctx.get("expression")
    if expression:
        parts.append(
            f'<div class="request-line"><span class="label">Expression</span><span class="val">{_esc(expression)}</span></div>'
        )

    # Source lines (syntax errors have lineno as highlight, runtime/undefined use snippet_error_line)
    source_lines = ctx.get("source_lines")
    highlight_line = ctx.get("snippet_error_line") or lineno
    if source_lines and highlight_line:
        parts.append(
            f'<div class="template-source">{_render_source_lines(source_lines, highlight_line)}</div>'
        )

    # Values (for runtime errors)
    values = ctx.get("values", {})
    if values:
        parts.append('<div class="template-values"><strong>Values:</strong>')
        for name, value in values.items():
            type_name = type(value).__name__
            value_repr = repr(value)
            if len(value_repr) > 80:
                value_repr = value_repr[:77] + "..."
            parts.append(
                f'<div class="local-var"><span class="name">{_esc(name)}</span><span class="value">{_esc(value_repr)} ({_esc(type_name)})</span></div>'
            )
        parts.append("</div>")

    # Variable name (for undefined errors)
    variable = ctx.get("variable")
    if variable:
        parts.append(
            f'<div class="request-line"><span class="label">Variable</span><span class="val">{_esc(variable)}</span></div>'
        )

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
            f"{_esc(error_code)} documentation</a></div>"
        )

    parts.append("</div>")
    return "".join(parts)


def _render_render_plan_panel(snapshot: dict[str, Any]) -> str:
    """Render stashed :class:`~chirp.templating.render_plan.RenderPlan` snapshot."""
    parts: list[str] = []
    parts.append('<div class="request-panel render-plan-panel">')
    parts.append(
        '<div class="request-line"><span class="label">Intent</span>'
        f'<span class="val">{_esc(snapshot.get("intent", ""))}</span></div>'
    )
    flags = (
        f"render_full_template={snapshot.get('render_full_template')!r}, "
        f"apply_layouts={snapshot.get('apply_layouts')!r}, "
        f"layout_start_index={snapshot.get('layout_start_index')!r}, "
        f"include_layout_oob={snapshot.get('include_layout_oob')!r}"
    )
    parts.append(
        f'<div class="request-line"><span class="label">Flags</span>'
        f'<span class="val">{_esc(flags)}</span></div>'
    )

    main = snapshot.get("main_view") or {}
    mt = main.get("template", "")
    mb = main.get("block", "")
    parts.append(
        '<div class="request-line"><span class="label">Main view</span>'
        f'<span class="val">{_esc(mt)} block {_esc(mb)}</span></div>'
    )

    preview = main.get("context_preview") or []
    if preview:
        parts.append('<div class="template-values"><strong>Main context</strong>')
        for name, value in preview:
            parts.append(
                f'<div class="local-var"><span class="name">{_esc(name)}</span>'
                f'<span class="value">{_esc(value)}</span></div>'
            )
        parts.append("</div>")

    chain = snapshot.get("layout_chain") or []
    if chain:
        parts.append("<h3>Layout chain (outer → inner)</h3>")
        parts.append('<div class="template-values">')
        for i, lay in enumerate(chain):
            tn = lay.get("template_name", "")
            tgt = lay.get("target", "")
            depth = lay.get("depth", "")
            parts.append(
                f'<div class="local-var"><span class="name">{i}</span>'
                f'<span class="value">{_esc(tn)} — target #{_esc(tgt)} (depth {_esc(depth)})</span></div>'
            )
        parts.append("</div>")

    applied = snapshot.get("layouts_applied") or []
    if applied:
        joined = " → ".join(str(x) for x in applied)
        parts.append(
            '<div class="request-line"><span class="label">Layouts applied</span>'
            f'<span class="val">{_esc(joined)}</span></div>'
        )

    lctx = snapshot.get("layout_context_preview") or []
    if lctx:
        parts.append('<div class="template-values"><strong>Layout context</strong>')
        for name, value in lctx:
            parts.append(
                f'<div class="local-var"><span class="name">{_esc(name)}</span>'
                f'<span class="value">{_esc(value)}</span></div>'
            )
        parts.append("</div>")

    regions = snapshot.get("region_updates") or []
    if regions:
        parts.append("<h3>Region updates</h3>")
        parts.append('<div class="template-values">')
        for ru in regions:
            line = (
                f"{ru.get('region', '')}: {ru.get('template', '')}"
                f"#{ru.get('block', '')} ({ru.get('mode', '')})"
            )
            parts.append(f'<div class="local-var"><span class="value">{_esc(line)}</span></div>')
        parts.append("</div>")

    parts.append(
        '<div class="exc-chain" style="margin-top:0.75rem">'
        "Snapshot taken after build_render_plan, before execute_render_plan."
        "</div>"
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
    parts.append(
        f'<div class="request-line"><span class="label">Request</span><span class="val">{_esc(method)} {_esc(path)} HTTP/{_esc(version)}</span></div>'
    )

    # Client
    client = ctx.get("client")
    if client:
        parts.append(
            f'<div class="request-line"><span class="label">Client</span><span class="val">{_esc(client)}</span></div>'
        )

    # Path params
    path_params = ctx.get("path_params")
    if path_params:
        pp = ", ".join(f"{k}={v!r}" for k, v in path_params.items())
        parts.append(
            f'<div class="request-line"><span class="label">Path Params</span><span class="val">{_esc(pp)}</span></div>'
        )

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
        parts.append(
            '<div class="request-line"><span class="label">Headers</span><span class="val">'
        )
        for name, value in headers:
            parts.append(f"{_esc(name)}: {_esc(value)}<br>")
        parts.append("</span></div>")

    parts.append("</div>")
    return "".join(parts)


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
        chain_note = (
            f"The above exception was the direct cause (raised from {type(cause).__name__})"
        )
    elif context:
        chain_note = f"During handling, another exception occurred ({type(context).__name__})"

    # Kida template error context — prefer cause when it has more specific location
    template_ctx = _extract_template_context(exc)
    if cause:
        cause_ctx = _extract_template_context(cause)
        if cause_ctx is not None:
            template_ctx = cause_ctx
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

    render_snap = read_render_debug_from_request(request)
    if render_snap:
        sections.append("<h2>Render plan</h2>")
        sections.append(_render_render_plan_panel(render_snap))

    # Traceback (with framework frame collapsing)
    if frames:
        sections.append("<h2>Traceback</h2>")
        collapsed = _collapse_framework_frames(frames)
        for item in collapsed:
            if isinstance(item, dict) and item.get("collapsed"):
                sections.append(_render_collapsed_frames(item))
            else:
                sections.append(_render_frame(item))

    # Request context
    sections.append("<h2>Request</h2>")
    sections.append(_render_request_panel(request))

    # Python / chirp / kida info
    sections.append("<h2>Environment</h2>")
    sections.append('<div class="request-panel">')
    sections.append(
        f'<div class="request-line"><span class="label">Python</span><span class="val">{_esc(sys.version)}</span></div>'
    )

    try:
        import chirp

        chirp_version = getattr(chirp, "__version__", "unknown")
    except Exception:
        chirp_version = "unknown"
    sections.append(
        f'<div class="request-line"><span class="label">Chirp</span><span class="val">{_esc(chirp_version)}</span></div>'
    )

    try:
        import kida

        kida_version = getattr(kida, "__version__", "unknown")
    except Exception:
        kida_version = "unknown"
    sections.append(
        f'<div class="request-line"><span class="label">Kida</span><span class="val">{_esc(kida_version)}</span></div>'
    )
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
        f'<meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_esc(qualified)}: {_esc(exc_message[:80])}</title>"
        f"<style>{_CSS}</style>"
        f"</head><body>"
        f'<div class="error-page">{body_html}</div>'
        f"<script>{_TOGGLE_JS}</script>"
        f"</body></html>"
    )
