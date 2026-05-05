"""Shared networked benchmark payloads."""

import sqlite3
import threading
from dataclasses import dataclass

JSON_PAYLOAD = {"message": "hello", "count": 42}
TEMPLATE_TITLE = "Benchmark Items"
DB_URI = "file:chirp_benchmark?mode=memory&cache=shared"
DB_QUERY_LIMIT = 10

_DB_LOCK = threading.Lock()
_DB_ANCHOR: sqlite3.Connection | None = None


@dataclass(frozen=True, slots=True)
class TemplateItem:
    name: str
    value: int


TEMPLATE_ITEMS = tuple(TemplateItem(name=f"Item {i}", value=i) for i in range(20))


@dataclass(frozen=True, slots=True)
class BenchmarkRow:
    id: int
    name: str
    score: int


DB_ROWS = tuple(BenchmarkRow(id=i, name=f"Row {i}", score=i * 7) for i in range(1, 101))

KIDA_TEMPLATE = """
<main>
  <h1>{{ title }}</h1>
  <ul>
    {% for item in items %}
    <li><span>{{ item.name }}</span><strong>{{ item.value }}</strong></li>
    {% end %}
  </ul>
</main>
""".strip()

JINJA_TEMPLATE = """
<main>
  <h1>{{ title }}</h1>
  <ul>
    {% for item in items %}
    <li><span>{{ item.name }}</span><strong>{{ item.value }}</strong></li>
    {% endfor %}
  </ul>
</main>
""".strip()


def cpu_work(iterations: int = 50_000) -> int:
    """CPU-bound work: repeated hashing."""
    h = 0
    for i in range(iterations):
        h = hash((h, i))
    return h


def ensure_sqlite_db() -> str:
    """Initialize the shared in-memory SQLite database for this process."""
    global _DB_ANCHOR
    with _DB_LOCK:
        if _DB_ANCHOR is not None:
            return DB_URI

        conn = sqlite3.connect(DB_URI, uri=True, check_same_thread=False)
        conn.execute(
            "CREATE TABLE benchmark_items (id INTEGER PRIMARY KEY, name TEXT NOT NULL, score INTEGER NOT NULL)"
        )
        conn.executemany(
            "INSERT INTO benchmark_items (id, name, score) VALUES (?, ?, ?)",
            ((row.id, row.name, row.score) for row in DB_ROWS),
        )
        conn.commit()
        _DB_ANCHOR = conn
        return DB_URI


def fetch_db_rows(limit: int = DB_QUERY_LIMIT) -> list[dict[str, int | str]]:
    """Run the benchmark SQLite query and return JSON-serializable rows."""
    uri = ensure_sqlite_db()
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, name, score
            FROM benchmark_items
            WHERE score >= ?
            ORDER BY score DESC
            LIMIT ?
            """,
            (100, limit),
        ).fetchall()
    return [dict(row) for row in rows]
