"""RAG-powered docs with streaming AI answers — zero JavaScript.

A documentation site where users can ask questions and get streaming
AI-generated answers with cited sources. The entire application is
~50 lines of Python. No React, no npm, no webpack. Just chirp + HTML.

Run::

    pip install chirp[ai,data]
    ollama pull llama3.2    # if using Ollama (default)
    ollama serve            # in another terminal
    python examples/rag_demo/app.py

Uses Ollama by default (no API key). Set CHIRP_LLM=anthropic:claude-sonnet-4-20250514 or ollama:llama3.2
and ANTHROPIC_API_KEY for cloud models.

Architecture::

    Browser (htmx)
        ↓ POST /ask
    Chirp handler
        ↓ db.fetch() — retrieve relevant docs
        ↓ llm.stream() — stream AI answer with context
        ↓ yield Fragment — re-rendered HTML block per token
    SSE → htmx swaps fragments into DOM

Lifecycle (multi-worker)::

    on_startup          → one-time schema migration + seeding (lifespan thread)
    on_worker_startup   → per-worker DB connection (worker's event loop)
    on_worker_shutdown  → per-worker DB disconnect
"""

import contextvars
import json
import os
import re
import secrets
import sys
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx

# Allow importing sync when run as script (python app.py)
sys.path.insert(0, str(Path(__file__).parent))

from sync import sync_from_sources

from urllib.parse import quote

from chirp import App, AppConfig, EventStream, Fragment, Request, SSEEvent, Template
from chirp.middleware.static import StaticFiles
from chirp.ai import LLM
from chirp.ai.streaming import stream_with_sources
from chirp.data import Database
from chirp.markdown import register_markdown_filter

# -- Helpers --


def _search_tokens(question: str) -> list[str]:
    """Extract searchable tokens from a question (alphanumeric, min 2 chars)."""
    stop = {"how", "do", "i", "to", "get", "a", "an", "the", "is", "are", "can", "what", "where"}
    words = re.findall(r"[a-zA-Z0-9]+", question.lower())
    return [w for w in words if len(w) >= 2 and w not in stop]


async def _retrieve_docs(db: Database | None, question: str) -> list[Document]:
    """Retrieve docs matching question tokens (content or title)."""
    if not db:
        return []
    tokens = _search_tokens(question)
    if not tokens:
        # Fallback: phrase match (escape % and _ for LIKE)
        escaped = question.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        return await db.fetch(
            Document,
            "SELECT id, title, content, url FROM docs WHERE content LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\' LIMIT 5",
            pattern,
            pattern,
        )
    # Token-based: match any token in content or title, order by match count
    conditions = " OR ".join(
        "(content LIKE ? OR title LIKE ?)" for _ in tokens
    )
    order = " + ".join(
        f"(CASE WHEN content LIKE ? OR title LIKE ? THEN 1 ELSE 0 END)"
        for _ in tokens
    )
    params: list[str] = []
    for t in tokens:
        params.extend([f"%{t}%", f"%{t}%"])
    params.extend(params)  # duplicate for ORDER BY
    sql = f"""
        SELECT id, title, content, url FROM docs
        WHERE {conditions}
        ORDER BY ({order}) DESC
        LIMIT 5
    """
    return await db.fetch(Document, sql, *params)


# -- Types --


@dataclass(frozen=True, slots=True)
class Document:
    """A documentation page stored in SQLite."""

    id: int
    title: str
    content: str
    url: str


@dataclass(frozen=True, slots=True)
class SharedQA:
    """A shared Q&A stored for share links."""

    id: int
    question: str
    answer: str
    sources_json: str
    slug: str


# -- Setup --

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
app = App(
    AppConfig(template_dir=TEMPLATES_DIR, debug=True, delegation=True)
)
app.add_middleware(StaticFiles(directory=STATIC_DIR, prefix="/static"))
_md_renderer = register_markdown_filter(app)


def _cite_filter(html: str, sources: list[Document] | None) -> str:
    """Replace [1], [2], etc. in HTML with links to sources."""
    if not sources:
        return html

    def repl(match: re.Match[str]) -> str:
        idx = int(match.group(1))
        if 1 <= idx <= len(sources):
            doc = sources[idx - 1]
            return f'<a href="{doc.url}" target="_blank" rel="noopener" class="citation">[{idx}]</a>'
        return match.group(0)

    return re.sub(r"\[(\d+)\]", repl, html)


@app.template_filter("cite")
def cite_filter(html: str, sources: list[Document] | None = None) -> str:
    """Replace [1], [2], etc. with links to sources. Use: {{ text | markdown | cite(sources) }}."""
    return _cite_filter(html, sources)

DB_PATH = Path(__file__).parent / "docs.db"
DB_URL = os.environ.get("DB_URL", f"sqlite:///{DB_PATH}")

# Per-worker database connection.  Each pounce worker thread runs its own
# asyncio event loop.  aiosqlite binds internal asyncio primitives to the
# loop where the connection is created, so we need one per worker.
_db_var: contextvars.ContextVar[Database | None] = contextvars.ContextVar(
    "rag_db",
    default=None,
)

# LLM is safe at module level — creates a fresh httpx.AsyncClient per
# request, no shared connection pool.
# Default: Ollama (no API key). Override with CHIRP_LLM=anthropic:claude-sonnet-4-20250514
_LLM_PROVIDER = os.environ.get("CHIRP_LLM", "ollama:llama3")
_IS_OLLAMA = _LLM_PROVIDER.startswith("ollama:")
_OLLAMA_BASE = os.environ.get("OLLAMA_BASE", "http://localhost:11434").rstrip("/")
llm = LLM(_LLM_PROVIDER)


async def _ollama_list_models() -> list[str]:
    """Fetch locally available Ollama models (like ollama/ example)."""
    try:
        async with httpx.AsyncClient(base_url=_OLLAMA_BASE, timeout=5.0) as client:
            resp = await client.get("/api/tags")
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


# -- Routes --


@app.route("/")
async def index() -> Template:
    """Render the docs homepage with search and model selector (when using Ollama)."""
    models: list[str] = []
    default_model = llm.model
    if _IS_OLLAMA:
        models = await _ollama_list_models()
        if models and default_model not in models:
            default_model = models[0]
    return Template(
        "index.html",
        title="Docs",
        models=models,
        default_model=default_model,
    )


@app.route("/share/{slug}", referenced=True)
async def share(slug: str) -> Template:
    """Render a read-only shared Q&A by slug."""
    db = _db_var.get()
    if not db:
        return Template("share.html", question="Error", answer="Database unavailable.", sources=[])
    row = await db.fetch_one(
        SharedQA,
        "SELECT id, question, answer, sources_json, slug FROM shared_qa WHERE slug = ?",
        slug,
    )
    if not row:
        return Template(
            "share.html",
            question="Not found",
            answer="This share link has expired or does not exist.",
            sources=[],
        )
    raw = json.loads(row.sources_json)
    sources = [SimpleNamespace(title=d["title"], url=d["url"], content=d.get("content", "")) for d in raw]
    return Template(
        "share.html",
        title=f"Shared: {row.question[:50]}…",
        question=row.question,
        answer=row.answer,
        sources=sources,
    )


@app.route("/ask", methods=["POST"])
async def ask(request: Request):
    """Handle form submit: return sources + scaffolding with sse-connect.

    Uses Ollama-style pattern: POST returns Fragment with sources and an
    answer div that opens SSE to /ask/stream for token-by-token delivery.
    Multi-line question = batch mode: one card per line.
    """
    form = await request.form()
    raw = (form.get("question") or "").strip()
    if not raw:
        return Fragment("ask.html", "empty_question")

    questions = [q.strip() for q in raw.split("\n") if q.strip()]
    if not questions:
        return Fragment("ask.html", "empty_question")

    model_name = (form.get("model") or "").strip() if _IS_OLLAMA else None
    model_b = (form.get("model_b") or "").strip() if _IS_OLLAMA else None
    compare = form.get("compare") == "on"

    db = _db_var.get()
    items: list[tuple[str, list[Document], str]] = []
    for q in questions:
        sources = await _retrieve_docs(db, q)
        stream_url = f"/ask/stream?question={quote(q)}"
        if model_name:
            stream_url += f"&model={quote(model_name)}"
        items.append((q, sources, stream_url))

    if compare and model_b and len(questions) == 1 and model_name != model_b:
        q, sources, _ = items[0]
        model_a = model_name or llm.model
        url_a = f"/ask/stream?question={quote(q)}&model={quote(model_a)}"
        url_b = f"/ask/stream?question={quote(q)}&model={quote(model_b)}"
        return Fragment(
            "ask.html",
            "ask_compare_result",
            question=q,
            sources=sources,
            stream_url_a=url_a,
            stream_url_b=url_b,
            model_a=model_a,
            model_b=model_b,
        )
    if len(items) == 1:
        q, sources, stream_url = items[0]
        return Fragment(
            "ask.html",
            "ask_result",
            question=q,
            sources=sources,
            stream_url=stream_url,
        )
    return Fragment("ask.html", "ask_batch_result", items=items)


@app.route("/ask/stream", referenced=True)
async def ask_stream(request: Request) -> EventStream:
    """SSE endpoint: stream AI answer token-by-token (Ollama pattern)."""

    async def generate():
        question = (request.query.get("question") or "").strip()
        model_name = (request.query.get("model") or "").strip() if _IS_OLLAMA else None
        llm_to_use = LLM(f"ollama:{model_name}") if model_name else llm

        if not question:
            yield Fragment("ask.html", "answer", text="No question provided.")
            yield SSEEvent(event="done", data="complete")
            return

        db = _db_var.get()
        sources = await _retrieve_docs(db, question)
        context = "\n\n".join(
            f"# {d.title}\nSource URL: {d.url}\n{d.content}" for d in sources
        )
        prompt = (
            f"You are a helpful documentation assistant. "
            f"Answer based ONLY on the following docs.\n\n{context}\n\n"
            f"Question: {question}\n\n"
            f"Answer concisely in markdown. Number your sources as [1], [2], [3], etc. "
            f"where [1] = first doc, [2] = second, etc. Use only these numbers when citing."
        )

        async def save_share(accumulated: str, srcs: list[Document], ctx: dict[str, Any]) -> str | None:
            db = _db_var.get()
            if not db:
                return None
            slug = secrets.token_urlsafe(8)
            sources_json = json.dumps(
                [{"title": d.title, "url": d.url, "content": d.content[:500]} for d in srcs]
            )
            await db.execute(
                "INSERT INTO shared_qa (question, answer, sources_json, slug) VALUES (?, ?, ?, ?)",
                ctx.get("question", ""),
                accumulated,
                sources_json,
                slug,
            )
            return slug

        def chunk_renderer(chunk: str) -> str:
            if not chunk:
                return ""
            return _cite_filter(_md_renderer.render(chunk), sources)

        async for frag in stream_with_sources(
            llm_to_use.stream(prompt),
            "ask.html",
            sources_block="sources",
            sources=sources,
            response_block="answer",
            extra_context={"question": question},
            share_link_block="share_link",
            on_complete=save_share,
            chunk_renderer=chunk_renderer,
        ):
            yield frag
        yield SSEEvent(event="done", data="complete")

    return EventStream(generate())


# -- Lifecycle --


# Default vertical stack docs (Bengal index.json format)
# Purr omitted — 404 until published
_DEFAULT_SOURCES = [
    "https://lbliii.github.io/bengal/index.json",
    "https://lbliii.github.io/chirp/index.json",
    "https://lbliii.github.io/pounce/index.json",
    "https://lbliii.github.io/kida/index.json",
    "https://lbliii.github.io/patitas/index.json",
    "https://lbliii.github.io/rosettes/index.json",
]


@app.on_startup
async def setup() -> None:
    """One-time schema migration and seeding (global lifespan).

    Creates a temporary DB connection to run DDL and seed data, then
    disconnects.  This runs once before workers are spawned.

    If RAG_DOC_SOURCES is set (comma-separated index.json URLs), syncs
    from those. Otherwise uses _DEFAULT_SOURCES. Falls back to sample
    docs only when no remote sources and table is empty.
    """
    db = Database(DB_URL)
    await db.connect()
    try:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS docs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                url TEXT NOT NULL,
                source TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS shared_qa (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                sources_json TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        # Add source column for existing DBs (no-op if already present)
        with suppress(Exception):
            await db.execute("ALTER TABLE docs ADD COLUMN source TEXT")

        sources_env = os.environ.get("RAG_DOC_SOURCES", "").strip()
        urls = (
            [u.strip() for u in sources_env.split(",") if u.strip()]
            if sources_env
            else _DEFAULT_SOURCES
        )

        if urls:
            print(f"downloading / indexing docs from {len(urls)} site indexes", flush=True)
            result = await sync_from_sources(db, urls)
            total = sum(c for c in result.values() if c > 0)
            print(f"ready ({total} docs)", flush=True)
        else:
            count = await db.fetch_val("SELECT COUNT(*) FROM docs")
            if count == 0:
                for title, content, url in _SAMPLE_DOCS:
                    await db.execute(
                        "INSERT INTO docs (title, content, url, source) VALUES (?, ?, ?, NULL)",
                        title,
                        content,
                        url,
                    )
                print("ready (sample docs)", flush=True)
    finally:
        await db.disconnect()


@app.on_worker_startup
async def worker_start() -> None:
    """Per-worker DB connection (bound to this worker's event loop)."""
    db = Database(DB_URL)
    await db.connect()
    _db_var.set(db)


@app.on_worker_shutdown
async def worker_stop() -> None:
    """Close per-worker DB connection."""
    db = _db_var.get()
    if db:
        await db.disconnect()
        _db_var.set(None)


# -- Sample data --

_SAMPLE_DOCS = [
    (
        "Getting Started",
        "Install chirp with pip install chirp. Create an app with App() "
        "and add routes with @app.route(). Run with app.run().",
        "/docs/getting-started",
    ),
    (
        "Templates",
        "Chirp uses kida for templates. Return Template('page.html', **context) "
        "from a route handler. Templates support Jinja2-compatible syntax with "
        "block inheritance and includes.",
        "/docs/templates",
    ),
    (
        "Fragments",
        "Return Fragment('page.html', 'block_name', **context) to render a "
        "single block from a template. Combined with htmx, this enables partial "
        "page updates without JavaScript. The server renders HTML, htmx swaps it.",
        "/docs/fragments",
    ),
    (
        "Streaming",
        "Return Stream('page.html', **async_context) for progressive rendering. "
        "The page shell renders immediately. Sections fill in as their data "
        "resolves. No loading spinners needed.",
        "/docs/streaming",
    ),
    (
        "Server-Sent Events",
        "Return EventStream(generator()) to push real-time updates. The generator "
        "yields Fragment objects that htmx swaps into the DOM. Zero client-side "
        "JavaScript required for real-time features.",
        "/docs/sse",
    ),
]

# ---------------------------------------------------------------------------
# Entry point — multi-worker Pounce for the full demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        from pounce import ServerConfig
        from pounce.server import Server

        app._ensure_frozen()
        server_config = ServerConfig(host="127.0.0.1", port=8000, workers=4)
        server = Server(server_config, app)
        print("RAG Demo — Streaming AI Answers")
        print("  http://127.0.0.1:8000")
        print("  4 worker threads (free-threading)")
        print()
        server.run()
    except ImportError:
        # Pounce not installed — fall back to single-worker dev server
        print("RAG Demo (single worker — install pounce for multi-worker)")
        app.run()
