"""Route explorer — debug-only HTML endpoint for inspecting discovered routes."""

from __future__ import annotations

import html
import inspect
import json
from typing import Any

ROUTE_EXPLORER_PATH = "/__chirp/routes"

_CSS = """\
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: ui-monospace, 'Cascadia Code', Menlo, monospace; background: #1a1b26;
  color: #a9b1d6; line-height: 1.6; padding: 2rem; font-size: 14px; }
h1 { color: #f7768e; font-size: 1.4rem; margin-bottom: 1rem; }
h2 { color: #7aa2f7; font-size: 1.1rem; margin: 1.5rem 0 0.5rem; border-bottom: 1px solid #2f3549; padding-bottom: 0.3rem; }
.route-row { padding: 8px 12px; margin: 4px 0; background: #24283b; border-radius: 4px; cursor: pointer; }
.route-row:hover { background: #2f3549; }
.route-path { color: #7dcfff; font-weight: bold; }
.route-meta { color: #9ece6a; font-size: 0.9rem; margin-top: 4px; }
.drill { background: #0d0e14; padding: 1rem; border-radius: 4px; margin-top: 0.5rem; font-size: 13px; }
.filter { margin-bottom: 1rem; }
.filter input { padding: 8px 12px; background: #0d0e14; border: 1px solid #333; border-radius: 4px;
  color: #a9b1d6; width: 300px; }
.badge { background: #565f89; padding: 2px 6px; border-radius: 4px; font-size: 0.8rem; margin-left: 4px; }
"""


def _esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def _route_to_dict(route: Any) -> dict[str, Any]:
    """Serialize a PageRoute to a JSON-serializable dict."""
    meta = route.meta
    meta_dict: dict[str, Any] = {}
    if meta is not None:
        meta_dict = {
            "title": meta.title,
            "section": meta.section,
            "breadcrumb_label": meta.breadcrumb_label,
            "shell_mode": meta.shell_mode,
        }
    layouts = []
    for lay in getattr(route.layout_chain, "layouts", ()):
        layouts.append({
            "template": getattr(lay, "template_name", ""),
            "target": getattr(lay, "target", ""),
            "depth": getattr(lay, "depth", 0),
        })
    providers = []
    for p in getattr(route, "context_providers", ()):
        providers.append({
            "path": getattr(p, "module_path", ""),
            "depth": getattr(p, "depth", 0),
        })
    actions = [{"name": getattr(a, "name", "")} for a in getattr(route, "actions", ())]
    handler_sig = ""
    try:
        sig = inspect.signature(route.handler, eval_str=True)
        handler_sig = str(sig)
    except Exception:
        handler_sig = "(inspect failed)"
    return {
        "url_path": route.url_path,
        "kind": getattr(route, "kind", "page"),
        "methods": list(getattr(route, "methods", [])),
        "template_name": route.template_name,
        "meta": meta_dict,
        "layout_count": len(layouts),
        "context_provider_count": len(providers),
        "action_count": len(actions),
        "has_viewmodel": route.viewmodel_provider is not None,
        "layouts": layouts,
        "providers": providers,
        "actions": actions,
        "handler_signature": handler_sig,
    }


def render_route_explorer(
    routes: list[Any],
    path_filter: str | None = None,
) -> str:
    """Render the route explorer HTML page."""
    filtered = routes
    if path_filter:
        pf = path_filter.lower().strip()
        filtered = [r for r in routes if pf in (getattr(r, "url_path", "") or "").lower()]

    route_dicts = [_route_to_dict(r) for r in filtered]
    path_param = path_filter or ""

    rows_html = []
    for rd in route_dicts:
        path = rd["url_path"]
        kind = rd["kind"]
        methods = ", ".join(rd["methods"])
        meta_str = json.dumps(rd["meta"]) if rd["meta"] else "{}"
        rows_html.append(
            f'<div class="route-row" data-path="{_esc(path)}">'
            f'<span class="route-path">{_esc(path)}</span>'
            f'<span class="badge">{_esc(kind)}</span>'
            f'<span class="badge">{_esc(methods)}</span>'
            f'<div class="route-meta">meta: {_esc(meta_str)}</div>'
            f'<div class="drill" style="display:none" data-detail="{_esc(json.dumps(rd))}">'
            f"<pre>{_esc(json.dumps(rd, indent=2))}</pre></div></div>"
        )

    filter_val = _esc(path_param)
    body = f"""
<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Chirp Route Explorer</title><style>{_CSS}</style></head><body>
<h1>Chirp Route Explorer</h1>
<p>{len(routes)} routes discovered. Debug-only.</p>
<div class="filter">
<form method="get" action="{ROUTE_EXPLORER_PATH}">
<input type="text" name="path" placeholder="Filter by path..." value="{filter_val}">
<button type="submit">Filter</button>
</form>
</div>
<h2>Routes</h2>
{"".join(rows_html)}
<script>
document.querySelectorAll(".route-row").forEach(function(row) {{
  row.addEventListener("click", function() {{
    var drill = row.querySelector(".drill");
    drill.style.display = drill.style.display === "none" ? "block" : "none";
  }});
}});
</script>
</body></html>"""
    return body
