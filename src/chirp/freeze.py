"""Freeze — render routes to static HTML files.

Walks the app's route table after freeze, renders each freezable URL
through the full ASGI middleware stack via TestClient, and writes the
output to disk.

URLs in the frozen HTML are rewritten from absolute (``/about``) to
relative (``../about/``) so the output works on any static host —
S3, GitHub Pages, Cloudflare, or plain ``file://`` — without a
server to resolve clean URLs.
"""

import json
import logging
import re
import shutil
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chirp.app import App

_logger = logging.getLogger(__name__)

_PARAM_RE = re.compile(r"\{(\w+)(?::\w+)?\}")

# Attributes that can contain internal URL paths.
_URL_ATTR_RE = re.compile(r'(href|action|hx-get|hx-post|hx-put|hx-delete|hx-patch)="(/[^"]*)"')


@dataclass(frozen=True, slots=True)
class FreezeResult:
    """Summary of a freeze run."""

    pages_written: int
    pages_skipped: int
    errors: list[str] = field(default_factory=list)
    urls: tuple[str, ...] = ()
    elapsed: float = 0.0


# ---------------------------------------------------------------------------
# Render-time search contributions
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SearchEntry:
    """Structured search data captured at render time.

    Route handlers call :func:`search_contribute` during freeze to
    register structured metadata for the current page.  This bypasses
    HTML scraping entirely — category, tags, TOC, and description
    survive from the template context to the search index.
    """

    url: str
    title: str
    description: str = ""
    category: str = ""
    tags: frozenset[str] = frozenset()
    toc: tuple[dict[str, Any], ...] = ()
    template_name: str = ""
    body: str = ""


_search_entries: ContextVar[list[SearchEntry] | None] = ContextVar(
    "chirp_freeze_search", default=None
)


def search_contribute(entry: SearchEntry) -> None:
    """Register a search contribution for the current freeze render.

    No-op outside of freeze (the ContextVar defaults to ``None``).
    """
    bucket = _search_entries.get(None)
    if bucket is not None:
        bucket.append(entry)


def _url_to_file_path(url: str, output_dir: Path) -> Path:
    """Map a URL path to an output file path.

    ``/docs/get-started/`` → ``output_dir/docs/get-started/index.html``
    ``/`` → ``output_dir/index.html``
    """
    stripped = url.strip("/")
    if stripped:
        return output_dir / stripped / "index.html"
    return output_dir / "index.html"


def _expand_params(route_path: str, params: dict[str, str]) -> str:
    """Replace ``{name}`` or ``{name:type}`` placeholders with values."""

    def _replace(m: re.Match[str]) -> str:
        return params[m.group(1)]

    return _PARAM_RE.sub(_replace, route_path)


def _make_relative(from_url: str, to_url: str) -> str:
    """Convert an absolute URL to a relative path to ``index.html``.

    Both arguments are absolute paths (e.g. ``/articles/foo``).
    The result is relative from the directory containing
    ``from_url/index.html`` and points to ``to_url/index.html``
    so that ``file://`` browsing works (no server-side index
    resolution needed).

    Examples::

        _make_relative("/articles/foo", "/about")
            # "../../about/index.html"
        _make_relative("/articles/foo", "/")
            # "../../index.html"
        _make_relative("/", "/about")
            # "about/index.html"
    """
    from_depth = len(from_url.strip("/").split("/")) if from_url.strip("/") else 0
    target = to_url.strip("/")
    prefix = "../" * from_depth
    if target:
        return prefix + target + "/index.html"
    return prefix + "index.html" if prefix else "index.html"


def _relativize_html(html: str, page_url: str, known_urls: frozenset[str]) -> str:
    """Rewrite absolute URL paths in *html* to relative paths.

    Only rewrites paths that match *known_urls* (the set of frozen
    pages).  External URLs, anchors, and unknown paths are left
    untouched.
    """

    def _replace(m: re.Match[str]) -> str:
        attr = m.group(1)
        url = m.group(2)
        # Split off fragment (#section) and query (?q=foo).
        bare = url.split("?")[0].split("#")[0]
        # Normalize: "/about" and "/about/" should both match.
        normalized = "/" + bare.strip("/") if bare != "/" else "/"
        if normalized not in known_urls:
            return m.group(0)
        relative = _make_relative(page_url, normalized)
        # Reattach fragment/query if present.
        suffix = url[len(bare) :]
        return f'{attr}="{relative}{suffix}"'

    return _URL_ATTR_RE.sub(_replace, html)


# ---------------------------------------------------------------------------
# Static search — client-side search for frozen output
# ---------------------------------------------------------------------------

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.DOTALL | re.IGNORECASE)
_ARTICLE_RE = re.compile(r"<article[^>]*>(.*?)</article>", re.DOTALL | re.IGNORECASE)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")

# Inline JS that powers client-side search on frozen pages.
# Reads the index from window.__chirp_search (loaded via <script src>),
# removes hx-* attrs from the search input (no live server), and filters
# results on keypress with a 300ms debounce.
_STATIC_SEARCH_JS = r"""(function(){
  var data=window.__chirp_search;if(!data)return;
  var entries=data.entries||data;
  var facets=data.facets||{};
  var inp=document.querySelector('.chirp-docs-search input[name="q"]');if(!inp)return;
  ['hx-get','hx-target','hx-swap','hx-trigger','hx-sync'].forEach(function(a){inp.removeAttribute(a)});
  var d=__DEPTH__,base='../'.repeat(d),timer,activeCat='';

  /* Build facet UI if categories exist */
  var facetHtml='';
  if(facets.category&&facets.category.length){
    facetHtml='<div class="chirp-search-facets"><select class="chirp-search-cat"><option value="">All categories</option>';
    facets.category.forEach(function(c){facetHtml+='<option value="'+esc(c)+'">'+esc(c)+'</option>';});
    facetHtml+='</select></div>';
    inp.parentNode.insertAdjacentHTML('afterend',facetHtml);
    var sel=inp.parentNode.parentNode.querySelector('.chirp-search-cat');
    if(sel)sel.addEventListener('change',function(){activeCat=this.value;doSearch();});
  }

  inp.addEventListener('input',function(){clearTimeout(timer);timer=setTimeout(doSearch,300)});
  function doSearch(){
    var q=inp.value.toLowerCase().trim(),el=document.getElementById('doc_list');if(!el)return;
    if(!q&&!activeCat){el.innerHTML='<p class="chirp-docs-no-results">Type to search documentation.</p>';return}

    /* Score and filter */
    var scored=[];
    entries.forEach(function(p){
      if(activeCat&&(p.c||'')!==activeCat)return;
      var s=0,tl=p.t.toLowerCase(),dl=(p.d||'').toLowerCase(),bl=(p.body||'').toLowerCase();
      if(q){
        if(tl.includes(q))s+=5;
        if(dl.includes(q))s+=3;
        if(bl.includes(q))s+=1;
        if(s===0)return;
      }else{s=1;}
      scored.push({s:s,p:p});
    });
    scored.sort(function(a,b){return b.s-a.s;});

    var h='';
    if(q)h+='<h2>Results for \u201c'+esc(q)+'\u201d</h2>';
    else if(activeCat)h+='<h2>'+esc(activeCat)+'</h2>';
    if(!scored.length){el.innerHTML=h+'<p class="chirp-docs-no-results">No pages found.</p>';return}
    h+='<ul>';
    for(var i=0;i<scored.length;i++){
      var p=scored[i].p;
      h+='<li><a href="'+base+p.u+'">';
      h+='<strong>'+esc(p.t)+'</strong>';
      if(p.d)h+='<span>'+esc(p.d)+'</span>';
      if(p.c)h+='<small class="chirp-search-cat-label">'+esc(p.c)+'</small>';
      h+='</a></li>';
    }
    el.innerHTML=h+'</ul>';
  }
  function esc(s){var e=document.createElement('span');e.textContent=s;return e.innerHTML}
})();"""


def _page_depth(url: str) -> int:
    """Return the directory depth of a URL path (for relative path computation)."""
    stripped = url.strip("/")
    return len(stripped.split("/")) if stripped else 0


_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.DOTALL | re.IGNORECASE)


def _extract_title(html: str) -> str:
    """Extract the page title from <title> or first <h1>."""
    m = _TITLE_RE.search(html)
    if m:
        return _TAG_STRIP_RE.sub("", m.group(1)).strip()
    m = _H1_RE.search(html)
    if m:
        return _TAG_STRIP_RE.sub("", m.group(1)).strip()
    return ""


def _extract_snippet(html: str, max_len: int = 200) -> str:
    """Extract a text snippet from the <article> element for search matching."""
    m = _ARTICLE_RE.search(html)
    if not m:
        return ""
    text = _TAG_STRIP_RE.sub(" ", m.group(1))
    text = " ".join(text.split())
    return text[:max_len]


def _build_search_index(rendered: list[tuple[str, str]]) -> list[dict[str, str]]:
    """Build a search index from rendered (url, html) pairs.

    Each entry has ``u`` (relative file path), ``t`` (title), and
    optionally ``d`` (text snippet for full-text matching).
    """
    index: list[dict[str, str]] = []
    for url, html in rendered:
        title = _extract_title(html)
        if not title:
            continue
        stripped = url.strip("/")
        file_path = (stripped + "/index.html") if stripped else "index.html"
        entry: dict[str, str] = {"u": file_path, "t": title}
        snippet = _extract_snippet(html)
        if snippet:
            entry["d"] = snippet
        index.append(entry)
    return index


def _build_rich_search_index(
    contributions: list[SearchEntry],
    rendered: list[tuple[str, str]],
) -> dict[str, Any]:
    """Build a structured search manifest from render-time contributions.

    Pages that contributed structured data via :func:`search_contribute`
    get full metadata (category, tags, TOC, description).  Pages without
    contributions fall back to HTML scraping for title + snippet.

    The manifest format::

        {
            "version": 1,
            "facets": {"category": [...], "tags": [...]},
            "entries": [{"u", "t", "d", "c", "tags", "toc", "body"}, ...]
        }
    """
    entries: list[dict[str, Any]] = []
    contributed_urls: set[str] = set()

    for contrib in contributions:
        normalized = "/" + contrib.url.strip("/") if contrib.url != "/" else "/"
        contributed_urls.add(normalized)
        contributed_urls.add(contrib.url)
        stripped = contrib.url.strip("/")
        file_path = (stripped + "/index.html") if stripped else "index.html"
        entry: dict[str, Any] = {"u": file_path, "t": contrib.title}
        if contrib.description:
            entry["d"] = contrib.description
        if contrib.category:
            entry["c"] = contrib.category
        if contrib.tags:
            entry["tags"] = sorted(contrib.tags)
        if contrib.toc:
            entry["toc"] = list(contrib.toc)
        if contrib.body:
            entry["body"] = contrib.body
        entries.append(entry)

    # Fallback: pages without contributions get HTML-scraped entries.
    for url, html in rendered:
        normalized = "/" + url.strip("/") if url != "/" else "/"
        if normalized in contributed_urls:
            continue
        title = _extract_title(html)
        if not title:
            continue
        stripped = url.strip("/")
        file_path = (stripped + "/index.html") if stripped else "index.html"
        entry = {"u": file_path, "t": title}
        snippet = _extract_snippet(html)
        if snippet:
            entry["d"] = snippet
        entries.append(entry)

    # Extract facets from contributed entries.
    categories = sorted({c.category for c in contributions if c.category})
    tags = sorted({t for c in contributions for t in c.tags})
    facets: dict[str, list[str]] = {}
    if categories:
        facets["category"] = categories
    if tags:
        facets["tags"] = tags

    return {"version": 1, "facets": facets, "entries": entries}


def _inject_static_search(html: str, depth: int, index_path: str) -> str:
    """Inject the client-side search script into a frozen HTML page.

    Only injects if the page contains a ``.chirp-docs-search`` input.
    Uses a ``<script src>`` for the index (works on ``file://``) and
    an inline script for the search logic.
    """
    if "chirp-docs-search" not in html:
        return html
    src_tag = f'<script src="{index_path}"></script>'
    js = _STATIC_SEARCH_JS.replace("__DEPTH__", str(depth))
    inline = f'<script data-chirp="static-search">{js}</script>'
    scripts = f"\n{src_tag}\n{inline}"
    if "</body>" in html:
        return html.replace("</body>", f"{scripts}\n</body>")
    # Pages without <body> (e.g. fragment-composed docs pages): append.
    return html + scripts


def _enumerate_urls(app: App) -> tuple[list[str], list[str], list[str]]:
    """Classify routes and expand parameterized ones.

    Returns (urls, skipped_reasons, warnings).
    """
    router = app._runtime_state.router
    if router is None:
        return [], ["No routes registered"], []

    urls: list[str] = []
    skipped: list[str] = []
    warnings: list[str] = []
    providers = app._mutable_state.freeze_param_providers
    excluded = app._mutable_state.freeze_exclude

    for route in router.routes:
        if "GET" not in route.methods:
            skipped.append(f"SKIP {route.path} (no GET method)")
            continue

        if route.path in excluded:
            skipped.append(f"SKIP {route.path} (freeze_exclude)")
            continue

        has_params = bool(_PARAM_RE.search(route.path))

        if not has_params:
            urls.append(route.path)
        else:
            provider = providers.get(route.path)
            if provider is None:
                warnings.append(
                    f"WARN {route.path}: parameterized route has no freeze_params provider, skipping"
                )
                skipped.append(f"SKIP {route.path} (no freeze_params)")
                continue
            param_sets = provider()
            for params in param_sets:
                expanded = _expand_params(route.path, params)
                urls.append(expanded)

    return urls, skipped, warnings


async def freeze(
    app: App,
    output_dir: Path,
    *,
    exclude: list[str] | None = None,
) -> FreezeResult:
    """Freeze the app to static HTML files.

    Renders every freezable GET route through the full ASGI stack
    and writes the output to *output_dir*.
    """
    from chirp.testing.client import TestClient

    t0 = time.monotonic()
    app._ensure_frozen()

    urls, skipped, warnings = _enumerate_urls(app)
    for w in warnings:
        _logger.warning(w)

    exclude_set = set(exclude) if exclude else set()
    filtered_urls: list[str] = []
    for url in urls:
        if any(url.startswith(pat) or url == pat for pat in exclude_set):
            skipped.append(f"SKIP {url} (excluded)")
        else:
            filtered_urls.append(url)

    output_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    # Phase 1: render all pages, collect HTML in memory.
    # Activate the search contribution ContextVar so route handlers can
    # register structured metadata during rendering.
    contributions: list[SearchEntry] = []
    token = _search_entries.set(contributions)
    rendered: list[tuple[str, str]] = []  # (url, html)

    try:
        async with TestClient(app) as client:
            for url in filtered_urls:
                try:
                    response = await client.get(url)
                except Exception as exc:
                    errors.append(f"ERROR {url}: {exc}")
                    _logger.exception("Failed to render %s", url)
                    continue

                if response.status != 200:
                    errors.append(f"ERROR {url}: status {response.status}")
                    _logger.warning("Non-200 for %s: %s", url, response.status)
                    continue

                ct = response.content_type or ""
                if "text/html" not in ct:
                    skipped.append(f"SKIP {url} (content-type: {ct})")
                    continue

                rendered.append((url, response.text))
    finally:
        _search_entries.reset(token)

    # Phase 2: rewrite absolute URLs → relative, inject static search, write to disk.
    known_urls = frozenset("/" + u.strip("/") if u != "/" else "/" for u, _ in rendered)
    written_urls: list[str] = []

    # Build search index — rich manifest if contributions exist, flat fallback otherwise.
    if contributions:
        manifest = _build_rich_search_index(contributions, rendered)
    else:
        manifest = _build_search_index(rendered)
    index_js = "window.__chirp_search=" + json.dumps(manifest, separators=(",", ":")) + ";"
    (output_dir / "_search-index.js").write_text(index_js)

    for url, html in rendered:
        normalized = "/" + url.strip("/") if url != "/" else "/"
        html = _relativize_html(html, normalized, known_urls)
        # Inject client-side search script (no-op if page has no search input).
        depth = _page_depth(url)
        index_rel = "../" * depth + "_search-index.js"
        html = _inject_static_search(html, depth, index_rel)
        out_path = _url_to_file_path(url, output_dir)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html)
        written_urls.append(url)

    # Copy static assets if configured.
    if app.config.static_dir:
        static_src = Path(app.config.static_dir)
        if static_src.is_dir():
            static_dest = output_dir / "static"
            if static_dest.exists():
                shutil.rmtree(static_dest)
            shutil.copytree(static_src, static_dest)

    elapsed = time.monotonic() - t0
    return FreezeResult(
        pages_written=len(written_urls),
        pages_skipped=len(skipped),
        errors=errors,
        urls=tuple(written_urls),
        elapsed=elapsed,
    )
