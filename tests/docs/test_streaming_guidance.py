"""Guards for streaming/SSE ownership guidance in docs."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_realtime_source_docs_name_product_owned_replay() -> None:
    text = _read("docs/realtime-production.md")

    assert "Last-Event-ID" in text
    assert "Chirp\nsupports `SSEEvent(id=...)`" in text
    assert "the product owns the cursor" in text
    assert "durable cursor storage remains product-owned" in text


def test_site_sse_docs_name_product_owned_replay() -> None:
    combined = "\n".join(
        (
            _read("site/content/docs/build-apps/streaming-updates/server-sent-events.md"),
            _read("site/content/docs/build-apps/streaming-updates/sse-patterns.md"),
        )
    )

    assert "Last-Event-ID" in combined
    assert "Chirp preserves `SSEEvent(id=...)`" in combined
    assert "product-owned durable cursor" in combined
    assert "the product owns the durable cursor" in combined
