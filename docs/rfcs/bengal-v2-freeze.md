# RFC: Bengal v2 as a Chirp Freeze Target

**Status:** Draft
**Date:** 2026-04-14

---

## Summary

Bengal v2 is not a new static site generator. It is Chirp with a `freeze` command. The same app that serves live pages with htmx navigation, Suspense streaming, and MCP tools can also emit static HTML by walking its own route table and writing rendered output to disk.

This inverts the standard approach to static sites: instead of starting with a build tool and bolting on dynamic features until you've rebuilt a framework, start with a real framework and project static output as one rendering mode.

## The Inversion

Every major SSG has followed the same trajectory:

1. Start as a content pipeline (markdown in, HTML out)
2. Users need dynamic features
3. Bolt on serverless functions, client-side hydration, islands, ISR
4. Eventually rebuild half a web framework inside the build tool

Gatsby added serverless functions and GraphQL. Next added ISR and server components. Astro added islands and server endpoints. Hugo added nothing, which is why people leave Hugo.

Chirp goes the other direction:

1. Start with a real framework (routing, middleware, request/response, templates, streaming)
2. Add a freeze command that projects static output from the existing app

The dynamic features aren't escape hatches. The static output is just one mode. This changes what's first-class:

| Traditional SSG | Chirp + Freeze |
|---|---|
| Static is native, dynamic is an escape hatch | Dynamic is native, static is a projection |
| Content pipeline is the architecture | App is the architecture, content is a plugin |
| Directives need parser plugins | Directives are template calls |
| Search needs a client-side index (lunr.js, pagefind) | Search is a route — freeze it or serve it live |
| API docs need a separate tool (Swagger, Redoc) | Autodoc introspects the same app |
| Dev server is a shim over the build output | Dev server is the real app |

## Why Freezing Is Fast

Traditional SSGs have a cold-start pipeline: read config, discover plugins, parse all content, build a dependency graph, compile templates, render, write. That's the entire job, every run.

Chirp's `DocsPlugin` (and any content-driven Chirp app) has already done 90% of that work by the time `app.freeze()` returns:

- **Markdown is parsed during `DocsCollection.load()`** — raw markdown becomes `DocPage` objects with `.html` ready to render
- **Kida templates are compiled at app init** — no re-parsing per page
- **Autodoc pages are generated in the startup hook** — route and tool introspection happens once
- **Navigation, search index, and TOC are built** — all computed during collection init
- **The full `DocPage` objects sit in memory** — title, slug, HTML, TOC, metadata

A freeze command would literally iterate pages, render each template with its context, and write files. The expensive work (markdown parsing, template compilation, route introspection) is already amortized into the normal server boot.

### Performance advantages over SSGs

- **No intermediate representation** — SSGs like Gatsby build a GraphQL data layer, Hugo builds a content graph. Chirp goes straight from markdown to rendered HTML in one pass during collection load.
- **No JS build step** — htmx is a CDN script. There's no webpack/vite/esbuild pass. That alone eliminates the slowest phase of Gatsby/Next/Astro static builds.
- **Free-threaded Python 3.14t** — the final render-to-disk step can parallelize across real threads with no GIL. Most SSGs are single-threaded or use process-level parallelism.
- **Incremental rebuild is trivial** — `DocPage` has `source_path` and slugs are tracked. Check mtimes against a manifest, skip unchanged pages.

The ceiling for a ~500 page site would probably be sub-second, because the work is just `template.render(doc=page, ...)` and writing strings to disk.

## Directive Handling

This is where the architecture pays off most clearly.

Traditional SSGs have two disconnected phases: markdown renders to HTML via a parser, then templates wrap the output. Directives (admonitions, code tabs, API parameter tables) must be handled entirely within the markdown parser via plugins (remark, markdown-it, etc.) before the template engine ever sees them. That's why MDX exists — to shove components back into markdown.

Chirp can short-circuit this. A directive in markdown can emit a Kida template call:

```markdown
:::note Warning
Don't do this in production.
:::

:::api-params endpoint="/contacts"
:::
```

During `DocsCollection.load()`, a pre-render pass transforms directives into Kida `{% call %}` or `{% include %}` blocks before the template engine compiles the page. The markdown isn't rendered to static HTML and then wrapped — it's rendered *through* the template engine.

This means:

- **Directives are template-aware** — a `:::toc:::` directive can read `doc.toc` directly rather than needing a separate parser plugin to inject it
- **Custom directives are just templates** — `:::note` maps to `{% include "directives/note.html" %}`, no Python plugin code needed
- **chirp-ui components work inside markdown** — if you have a card component, a directive emits it directly
- **Context flows down** — a directive can reference `docs_prefix`, the current page's category, anything in template scope

For a static freeze, directives don't add a pipeline stage. Directive expansion happens during the same render pass — it's part of template compilation, which Kida already optimizes. Traditional SSG directive plugins run as a separate AST transform over every page.

## The Development Story

```bash
chirp dev            # Live server — htmx, hot reload, Suspense, MCP tools
chirp freeze dist/   # Walk routes, render, write static HTML
chirp serve dist/    # Preview frozen output locally
```

During development you get the full framework: fragment navigation, streaming responses, live search, AI agent tools. When you're ready to ship a static site, `freeze` projects the same content as flat files.

## Progressive Enhancement Works Both Ways

The frozen output doesn't have to strip dynamic features. htmx attributes can stay in the HTML. If someone later puts a Chirp server in front of the static files:

- Fragment navigation just works (htmx `hx-get` attributes are already in the markup)
- Search can freeze as a static page with a form, then progressively enhance to live htmx search when served dynamically
- The MCP endpoint activates when the server is running, invisible when static

You don't have to choose static vs dynamic up front. The same codebase supports both, and the frozen output is designed to upgrade gracefully.

## Freeze Mechanics (Sketch)

The return type system makes freeze behavior unambiguous:

| Return Type | Freeze Behavior |
|---|---|
| `Page(template, block, **ctx)` | Render full page HTML, write to `{slug}/index.html` |
| `Template(template, **ctx)` | Render as-is, write to path |
| `Fragment(...)` | Skip — dynamic-only endpoint |
| `EventStream(...)` | Skip — requires live connection |
| `Suspense(...)` | Resolve all deferred values, render complete page |
| `FormAction(...)` | Skip — requires POST handling |

The router already knows every URL path. For parameterized routes (like `/docs/{slug:path}`), the freeze needs a way to enumerate values — which content collections already provide via their page lists.

```python
# Possible API
@app.freeze_params("/docs/{slug:path}")
def docs_params():
    return [{"slug": p.slug} for p in collection.pages]
```

Static assets copy from `static/` to the output directory. CSS, images, fonts — no transformation needed.

## What This Means for Bengal

Bengal v1 is a standalone SSG. It has its own content pipeline, its own template loading, its own CLI. It works, but it's a parallel universe to Chirp.

Bengal v2 would be:

- **A Chirp plugin or CLI extension**, not a separate tool
- **Content is a `DocsPlugin`** (or a similar content plugin), not a custom pipeline
- **Themes are Kida templates**, same as any Chirp app
- **The freeze command** is the "build" step
- **Dev mode** is just `chirp dev` — the same live server any Chirp app uses

The SSG features (content collections, frontmatter, taxonomies, pagination) live in Chirp plugins. The freeze command is framework-level. Bengal v2 is the name for "Chirp apps that happen to freeze well" — a pattern, not a separate product.

## Open Questions

1. **How should freeze discover all renderable URLs?** Content plugins can enumerate their pages, but arbitrary dynamic routes need explicit param providers. What's the right registration API?

2. **Frozen search** — should the freeze emit a static search index (JSON) for client-side search (pagefind-style), or is search purely a server feature? Could offer both: freeze a search index file, use it client-side when static, use the live route when served.

3. **Incremental freeze** — mtime-based diffing against a manifest is simple but doesn't catch template changes. Should the freeze hash template sources too?

4. **Asset pipeline** — Chirp currently serves static files as-is. Should freeze support optional CSS/JS minification, or is that out of scope (use external tools)?

5. **Sitemap / feeds** — these are standard SSG outputs. Should they be built into the freeze command or left to plugins?

6. **Multi-format output** — could the same freeze produce HTML + a JSON API (for headless CMS patterns)? The `DocPage` model already has `.raw` markdown and structured metadata.
