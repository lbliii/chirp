"""RAG-powered docs with streaming AI answers — zero JavaScript.

A documentation site where users can ask questions and get streaming
AI-generated answers with cited sources. The entire application is
~50 lines of Python. No React, no npm, no webpack. Just chirp + HTML.

Run::

    pip install chirp[ai,data]
    python examples/rag_demo/app.py

Architecture::

    Browser (htmx)
        ↓ POST /ask
    Chirp handler
        ↓ db.fetch() — retrieve relevant docs
        ↓ llm.stream() — stream AI answer with context
        ↓ yield Fragment — re-rendered HTML block per token
    SSE → htmx swaps fragments into DOM
"""

from dataclasses import dataclass

from chirp import App, AppConfig, EventStream, Fragment, Template
from chirp.ai import LLM
from chirp.ai.streaming import stream_with_sources
from chirp.data import Database

# -- Types --


@dataclass(frozen=True, slots=True)
class Document:
    """A documentation page stored in SQLite."""

    id: int
    title: str
    content: str
    url: str


# -- Setup --

app = App(AppConfig(template_dir="examples/rag_demo/templates", debug=True))
db = Database("sqlite:///examples/rag_demo/docs.db")
llm = LLM("anthropic:claude-sonnet-4-20250514")


# -- Routes --


@app.route("/")
def index() -> Template:
    """Render the docs homepage with search."""
    return Template("index.html", title="Docs")


@app.route("/ask", methods=["POST"])
async def ask(request) -> EventStream:
    """Stream an AI answer with cited sources.

    1. Query SQLite for matching documents (data layer)
    2. Stream Claude's answer with those docs as context (AI layer)
    3. Push HTML fragments via SSE (htmx swaps them in)
    """
    question = (await request.form())["question"]

    # Data: find relevant documents
    sources = await db.fetch(
        Document,
        "SELECT id, title, content, url FROM docs WHERE content LIKE ? LIMIT 5",
        f"%{question}%",
    )

    # AI: stream answer with context
    context = "\n\n".join(f"# {d.title}\n{d.content}" for d in sources)
    prompt = (
        f"You are a helpful documentation assistant. "
        f"Answer based on the following docs:\n\n{context}\n\n"
        f"Question: {question}\n\n"
        f"Answer concisely in markdown."
    )

    return EventStream(stream_with_sources(
        llm.stream(prompt),
        "ask.html",
        sources_block="sources",
        sources=sources,
        response_block="answer",
    ))


# -- Lifecycle --


@app.on_startup
async def setup() -> None:
    """Initialize the database with sample docs."""
    await db.connect()
    await db.execute("""
        CREATE TABLE IF NOT EXISTS docs (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            url TEXT NOT NULL
        )
    """)
    # Seed sample data if empty
    count = await db.fetch_val("SELECT COUNT(*) FROM docs")
    if count == 0:
        for title, content, url in _SAMPLE_DOCS:
            await db.execute(
                "INSERT INTO docs (title, content, url) VALUES (?, ?, ?)",
                title, content, url,
            )


@app.on_shutdown
async def teardown() -> None:
    """Close database connections."""
    await db.disconnect()


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

if __name__ == "__main__":
    app.run()
