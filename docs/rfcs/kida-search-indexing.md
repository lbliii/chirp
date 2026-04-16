# RFC: Template-Engine-Aware Search Indexing

**Status:** Proposal  
**Authors:** Chirp team  
**Audience:** Kida template engine developers  
**Date:** 2025-04-15

## Summary

We propose that Kida add first-class support for **render-time data capture** — the ability to collect structured metadata (block-level content, context variables, template identity) as a side effect of rendering, with zero overhead when disabled. This would make Kida the first template engine that can generate a search index as a natural byproduct of rendering, rather than requiring post-hoc HTML scraping.

## Background

### The problem

Chirp has a `freeze` command that renders an app's routes to static HTML for deployment on S3, GitHub Pages, or `file://`. The frozen output needs a client-side search index. Today, this index is built by scraping rendered HTML with regex:

```python
# Current approach: regex extraction from HTML output
def _build_search_index(rendered: list[tuple[str, str]]) -> list[dict]:
    for url, html in rendered:
        title = _extract_title(html)      # <title> or <h1> regex
        snippet = _extract_snippet(html)   # first 200 chars of <article>
        index.append({"url": url, "title": title, "snippet": snippet})
```

This throws away everything the template engine knew at render time:

| Data | Available during render | Survives to search index |
|------|------------------------|-------------------------|
| Page title | `doc.title` | Recovered via `<title>` regex |
| Description | `doc.metadata.description` | Lost |
| Category | `doc.metadata.category` | Lost |
| Tags | `doc.metadata.tags` | Lost |
| TOC structure | `doc.toc` (heading IDs, levels, text) | Lost |
| Block boundaries | Template block names + roles | Lost |
| Template identity | Which template rendered this page | Lost |
| Raw content | `doc.raw` (markdown source) | Approximated via `<article>` text strip |

The template engine is the **only component** that sees both the structured data and the output shape simultaneously. Everything downstream (HTML parsers, text extractors, embedding models) is trying to recover what the template already knew.

### What we built as a workaround

We added a `ContextVar`-based contribution system **outside Kida** in the Chirp framework layer:

```python
# In chirp/freeze.py
_search_entries: ContextVar[list[SearchEntry] | None] = ContextVar(
    "chirp_freeze_search", default=None
)

def search_contribute(entry: SearchEntry) -> None:
    bucket = _search_entries.get(None)
    if bucket is not None:
        bucket.append(entry)
```

Route handlers manually call `search_contribute()` to register structured metadata:

```python
# In chirp/docs/plugin.py — inside the docs_page route handler
search_contribute(SearchEntry(
    url=f"{prefix}/{slug}",
    title=doc.title,
    description=doc.metadata.description,
    category=doc.metadata.category,
    tags=doc.metadata.tags,
    toc=tuple({"level": e.level, "id": e.id, "text": e.text} for e in doc.toc),
    template_name="chirp_docs/doc_page.html",
    body=doc.raw[:500],
))
```

**This works**, and the resulting search manifest is dramatically richer than HTML scraping:

```json
{
  "version": 1,
  "facets": {
    "category": ["Articles", "Meta"],
    "tags": ["architecture", "chirp", "deployment", "htmx", "streaming"]
  },
  "entries": [
    {
      "u": "docs/why-hypermedia/index.html",
      "t": "Why Hypermedia?",
      "d": "The case for returning HTML instead of JSON.",
      "c": "Articles",
      "tags": ["architecture", "htmx"],
      "toc": [
        {"level": 1, "id": "why-hypermedia", "text": "Why Hypermedia?"},
        {"level": 2, "id": "the-problem-with-spas", "text": "The Problem with SPAs"}
      ],
      "body": "# Why Hypermedia?\n\nHypermedia is the original architecture of the web..."
    }
  ]
}
```

**But the template engine isn't participating.** The route handler is doing all the work — manually copying fields from application data models into search entries. The template's block structure, inferred roles, and dependency information are unused. If the data model gains a field, someone has to remember to update the `search_contribute()` call.

## The opportunity

Kida already has the infrastructure to make this better. It just doesn't expose it for this purpose yet.

### What Kida already knows

**At compile time** (via `template_metadata()` / `block_metadata()`):

```
BlockMetadata:
  name: "doc_content"
  inferred_role: "content"          ← block is the main content region
  depends_on: {"doc.html", "doc"}   ← context paths this block reads
  emits_landmarks: {"article"}      ← HTML landmarks emitted
  is_pure: "pure"                   ← deterministic for same inputs
  cache_scope: "page"               ← varies per page
  block_hash: "a1b2c3..."           ← structural fingerprint

TemplateMetadata:
  name: "chirp_docs/doc_page.html"
  extends: None
  blocks: {"doc_content": ..., "doc_sidebar": ..., "doc_toc": ...}
  top_level_depends_on: {"docs_prefix", "docs_nav_items"}
```

This is a **structural schema** of every page rendered through this template. Block names are semantic regions. `inferred_role` classifies them. `depends_on` lists the context variables that feed each block.

**At render time** (accessible but not captured):

- The full context dict passed to `render()` — all template variables
- The rendered output of each block (available via `render_block()`)
- The template name and inheritance chain
- The `RenderContext._meta` dict (framework metadata like request headers)

**At profiling time** (via `RenderAccumulator` when `enable_profiling=True`):

- Block render timings and call counts
- Macro call counts
- Include/embed counts
- Filter usage

The profiling system proves the pattern works — opt-in, ContextVar-based, zero overhead when disabled, compiler-injected hooks. It just captures **timing**, not **content or context**.

### What's missing

There is no way to say "during this render, also capture the rendered text of each block and the context values that fed it." The `RenderAccumulator` captures *performance* metrics. We need something analogous for *content* metrics — or more precisely, for **structured data extraction** from the render pass.

## Proposal

### Option A: Extend RenderAccumulator with content capture

Add optional content recording to the existing accumulator pattern:

```python
# New fields on RenderAccumulator (or a new ContentAccumulator)
@dataclass
class RenderAccumulator:
    # ... existing timing fields ...
    
    # NEW: opt-in content capture
    block_outputs: dict[str, str] | None = None    # block_name → rendered HTML
    context_snapshot: dict[str, Any] | None = None  # captured context keys
    
    def record_block_output(self, name: str, html: str) -> None:
        if self.block_outputs is not None:
            self.block_outputs[name] = html
    
    def record_context(self, ctx: dict[str, Any], keys: frozenset[str]) -> None:
        if self.context_snapshot is not None:
            self.context_snapshot = {k: ctx[k] for k in keys if k in ctx}
```

The compiler would inject `record_block_output()` calls alongside existing `record_block()` timing calls (when `enable_profiling=True`). The content fields default to `None` — only populated when the caller opts in:

```python
with profiled_render(capture_content=True) as metrics:
    html = template.render(page=page)

# After render:
print(metrics.block_outputs["doc_content"])  # rendered content block HTML
print(metrics.context_snapshot["doc"])        # the doc object from context
```

**Pros:** Minimal API surface. Reuses existing infrastructure. Same zero-overhead contract.  
**Cons:** Couples search concerns to profiling. Content capture allocates strings per block, which is heavier than timing.

### Option B: New `RenderCapture` alongside `RenderAccumulator`

A separate ContextVar-based capture system, purpose-built for content extraction:

```python
# kida/render_capture.py

@dataclass
class BlockCapture:
    name: str
    role: str                    # from BlockMetadata.inferred_role
    text: str                    # stripped text (HTML tags removed)
    html: str                    # raw rendered HTML
    depends_on: frozenset[str]   # from BlockMetadata.depends_on

@dataclass
class RenderCapture:
    template_name: str
    blocks: dict[str, BlockCapture] = field(default_factory=dict)
    context_keys: dict[str, Any] = field(default_factory=dict)

_capture: ContextVar[RenderCapture | None] = ContextVar("render_capture", default=None)

@contextmanager
def captured_render(
    capture_blocks: frozenset[str] | None = None,  # None = all blocks
    capture_context: frozenset[str] | None = None,  # context keys to snapshot
    strip_html: bool = True,
) -> Iterator[RenderCapture]:
    ...
```

Usage from a framework:

```python
with captured_render(
    capture_blocks=frozenset({"doc_content", "doc_toc"}),
    capture_context=frozenset({"doc", "docs_prefix"}),
) as capture:
    html = template.render(doc=doc, docs_prefix="/docs")

# capture.blocks["doc_content"].text → "Why Hypermedia? Hypermedia is..."
# capture.blocks["doc_content"].role → "content"
# capture.context_keys["doc"] → the DocPage object
```

The compiler would need a new flag (e.g., `enable_capture=True`) or could piggyback on `enable_profiling=True` to inject the capture hooks.

**Pros:** Clean separation of concerns. Purpose-built API. Can evolve independently from profiling.  
**Cons:** New ContextVar, new compiler flag, more API surface.

### Option C: Block render hooks (most general)

Rather than building capture into the compiler, expose a hook that fires after every block render:

```python
# On Environment or Template:
def on_block_rendered(
    callback: Callable[[str, str, dict[str, Any]], None]
) -> None:
    """Register a callback fired after each block renders.
    
    Args:
        callback(block_name, rendered_html, context): Called after each block.
    """
```

The compiler injects the hook call after each block's `''.join(buf)`:

```python
def _block_doc_content(ctx, _blocks):
    buf = []
    # ... render block ...
    result = ''.join(buf)
    
    # Injected hook (only if hooks registered):
    _on_block(name="doc_content", html=result, ctx=ctx)
    
    return result
```

Frameworks build whatever capture/indexing logic they want on top:

```python
index = []

def on_block(name, html, ctx):
    if name == "doc_content":
        index.append({"content": strip_html(html), "title": ctx.get("doc", {}).title})

env.on_block_rendered(on_block)
html = template.render(doc=doc)
```

**Pros:** Most flexible. Frameworks control what's captured. No new dataclass.  
**Cons:** Per-block function call overhead (even if minimal). Callback-based API can be harder to reason about. Needs careful design for the hook signature.

### Option D: Template-level `__search_schema__` (static, no runtime hooks)

The lightest option — no runtime capture at all. Instead, expose template metadata in a way that frameworks can use to build index schemas:

```python
meta = template.template_metadata()

schema = {}
for name, block in meta.blocks.items():
    schema[name] = {
        "role": block.inferred_role,
        "depends_on": sorted(block.depends_on),
        "cache_scope": block.cache_scope,
    }

# schema = {
#   "doc_content": {"role": "content", "depends_on": ["doc", "doc.html"], ...},
#   "doc_sidebar": {"role": "sidebar", "depends_on": ["docs_nav_items"], ...},
#   "doc_toc": {"role": "navigation", "depends_on": ["doc", "doc.toc"], ...},
# }
```

Frameworks combine this with their own application-level metadata (which they already have in the route handler) to build the index. Kida's contribution is telling them *what the template's blocks mean* — their roles, dependencies, and structure — so the framework knows which context variables map to which semantic regions.

**Pros:** No runtime overhead. No new compiler flags. Uses existing `template_metadata()` API.  
**Cons:** Doesn't capture rendered block content. Framework still does the mapping manually.

## Recommendation

We think **Option B** is the right level of abstraction, with **Option D** as a complement.

Option B (`RenderCapture`) gives frameworks a clean, purpose-built way to capture block-level content during render. It follows the same pattern as `RenderAccumulator` — ContextVar, opt-in, zero overhead when unused — but serves a different purpose: content extraction rather than performance profiling.

Option D is already available today via `template_metadata()` and gives frameworks the structural schema without any runtime cost. It's the "tell me what your blocks mean" API.

Together, these two capabilities let a framework build a search index that:

1. **Knows the template schema** (via `template_metadata()`) — which blocks exist, their semantic roles, their dependencies
2. **Captures block content during render** (via `captured_render()`) — the actual text of each block, tagged with its role
3. **Snapshots context values** (via `capture_context`) — the structured data that fed the render, before it became HTML

This is the "moment of maximum information" — the template engine has the data, the structure, and the output all at once. No downstream HTML parser can reconstruct this.

## What this enables

### For static site generators (like Chirp freeze)

Instead of this:

```python
# Post-hoc: scrape rendered HTML with regex
title = re.search(r"<title>(.*?)</title>", html).group(1)
snippet = re.search(r"<article>(.*?)</article>", html).group(1)[:200]
```

You get this:

```python
# Render-time: structured data captured alongside output
with captured_render(capture_blocks={"doc_content"}) as cap:
    html = template.render(doc=doc, nav=nav)

index_entry = {
    "title": doc.title,           # from context (no parsing)
    "content": cap.blocks["doc_content"].text,  # block text, role-tagged
    "role": cap.blocks["doc_content"].role,      # "content" (from template schema)
}
```

### For search with semantic weighting

Block roles enable automatic relevance weighting:

```python
weights = {"content": 3, "sidebar": 0.5, "navigation": 0, "footer": 0}
for name, block in capture.blocks.items():
    score += match(query, block.text) * weights.get(block.role, 1)
```

The template author defines what "content" and "sidebar" mean by naming their blocks. The search engine uses that structure without any configuration.

### For faceted search

Template metadata reveals what dimensions exist:

```python
meta = template.template_metadata()
content_block = meta.get_block("doc_content")
# content_block.depends_on = {"doc", "doc.html", "doc.toc"}
# → "doc" is a page-specific variable → this block varies per page
# → facets come from the context (doc.metadata.category, doc.metadata.tags)
```

The template schema tells you that pages through this template have a `doc` object with certain fields. Those fields become search facets automatically.

### For vector/embedding pipelines

Block boundaries are natural chunk boundaries for RAG:

```python
for name, block in capture.blocks.items():
    if block.role == "content":
        chunks.append(Chunk(
            text=block.text,
            metadata={"template": meta.name, "block": name, "role": block.role},
        ))
```

Template blocks are author-defined semantic units — better chunk boundaries than token-count splitters.

## Existing Kida infrastructure this builds on

| Component | File | What it provides |
|-----------|------|-----------------|
| `RenderAccumulator` | `kida/render_accumulator.py` | ContextVar pattern, `profiled_render()` context manager, zero-overhead-when-disabled contract |
| `BlockMetadata` | `kida/analysis/metadata.py` | `inferred_role`, `depends_on`, `cache_scope`, `emits_landmarks` |
| `TemplateMetadata` | `kida/analysis/metadata.py` | `blocks: dict[str, BlockMetadata]`, `extends`, `all_dependencies()` |
| `RenderContext._meta` | `kida/render_context.py` | Framework metadata dict, inherited through includes/extends |
| `Extension` | `kida/extensions.py` | Custom tags, `parse()` → AST nodes, `compile()` → Python AST injection |
| `enable_profiling` | `kida/compiler/core.py` | Compile-time flag that injects profiling AST (block timing, filter counts) |
| `template.render_block()` | `kida/template/core.py` | Render individual blocks independently |
| `template.list_blocks()` | `kida/template/core.py` | Enumerate available blocks |

The `RenderAccumulator` pattern is the closest precedent. It proves:
- ContextVar-based opt-in capture works
- Compiler-injected hooks have zero overhead when disabled
- The `@contextmanager` + `ContextVar` pattern is ergonomic

The difference: `RenderAccumulator` captures **when** and **how often** blocks render. `RenderCapture` would capture **what** they render and **what data fed them**.

## Open questions for Kida developers

1. **Compiler flag:** Should content capture reuse `enable_profiling=True` or get its own flag (e.g., `enable_capture=True`)? Profiling and capture are conceptually different — you might want timing without content, or content without timing.

2. **Block output interception:** The compiler currently generates `return ''.join(buf)` at the end of each block function. Capture would need to intercept that return value. Is the preferred approach:
   - Wrapping the block call site (where `_blocks.get('name', _block_name)(ctx, _blocks)` is called)?
   - Injecting a recording call before the `return` in each block function?
   - Using the existing `_append` function replacement pattern?

3. **Context snapshot scope:** Capturing the full context dict is wasteful. Should capture be limited to keys listed in `BlockMetadata.depends_on`? Or should frameworks specify which keys to capture (like `capture_context=frozenset({"doc", "docs_prefix"})`)?

4. **Text stripping:** Should Kida strip HTML from captured block content, or return raw HTML and let frameworks strip it? Stripping is useful for search but lossy for other use cases.

5. **Performance budget:** Content capture allocates strings per block per render. For a 100-page freeze this is trivial. For a hot path serving live requests, it could matter. Should the API discourage live-request usage, or is the ContextVar opt-in sufficient?

6. **Streaming renders:** Chirp uses `Suspense` (streaming deferred blocks via SSE). Should capture work with streaming renders, or is batch render (`template.render()`) sufficient for the initial version?

## Appendix: Chirp's current workaround

For reference, here is the full working implementation in Chirp that this RFC proposes to improve with Kida-level support.

### `SearchEntry` + `search_contribute()` (framework-level ContextVar)

```python
# src/chirp/freeze.py

@dataclass(frozen=True, slots=True)
class SearchEntry:
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
    bucket = _search_entries.get(None)
    if bucket is not None:
        bucket.append(entry)
```

### DocsPlugin integration (manual field mapping)

```python
# src/chirp/docs/plugin.py — inside docs_page route handler

search_contribute(SearchEntry(
    url=f"{normalized_prefix}/{slug}",
    title=doc.title,
    description=doc.metadata.description,
    category=doc.metadata.category,
    tags=doc.metadata.tags,
    toc=tuple({"level": e.level, "id": e.id, "text": e.text} for e in doc.toc),
    template_name=f"{_TEMPLATE_NS}/doc_page.html",
    body=doc.raw[:500],
))
```

### Rich search manifest output

```python
# src/chirp/freeze.py

def _build_rich_search_index(contributions, rendered):
    manifest = {"version": 1, "facets": {...}, "entries": [...]}
    
    # Contributed pages get full structured metadata
    for contrib in contributions:
        entry = {"u": ..., "t": contrib.title, "d": contrib.description,
                 "c": contrib.category, "tags": sorted(contrib.tags),
                 "toc": list(contrib.toc), "body": contrib.body}
    
    # Pages without contributions fall back to HTML scraping
    for url, html in rendered:
        if url not in contributed_urls:
            entry = {"u": ..., "t": _extract_title(html), "d": _extract_snippet(html)}
    
    return manifest
```

### What Kida-level support would replace

With `captured_render()`, the DocsPlugin integration would become:

```python
# Hypothetical — with Kida-level RenderCapture

# No manual field mapping needed. The template engine captures
# block content and context during render.
with captured_render(
    capture_blocks=frozenset({"doc_content", "doc_toc"}),
    capture_context=frozenset({"doc"}),
) as capture:
    html = template.render(doc=doc, docs_nav_items=nav, docs_prefix=prefix)

# The capture has everything:
# - capture.blocks["doc_content"].text → stripped article text
# - capture.blocks["doc_content"].role → "content"
# - capture.blocks["doc_toc"].text → TOC text
# - capture.context_keys["doc"] → the DocPage object (with title, category, tags, toc)
# - capture.template_name → "chirp_docs/doc_page.html"
```

The route handler wouldn't need to know about search at all. The freeze pipeline would capture everything it needs from the render itself.
