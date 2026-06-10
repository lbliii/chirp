"""In-process ASGI chunk-framing assertions for streaming response types.

Real socket binding is unavailable in this CI sandbox (see
``tests/test_worker_lifecycle.py``), so these tests assert the *structure* and
*ordering* of the ASGI body messages a streaming response emits — captured in
memory via ``TestClient.request_chunks`` / ``CapturedStream`` — rather than
wall-clock timing (which would need a socket and be flaky).

For ``Stream`` / ``TemplateStream`` / ``Suspense`` we assert:

* the body arrives as **more than one** ``http.response.body`` chunk — a
  regression that collapses streaming into one buffered render fails here;
* the **shell / earlier** bytes arrive **before** the deferred / streamed-block
  bytes (ordering);
* key markers land in the **expected** chunk.

A buffered ``Response`` control case proves the helper does *not* vacuously
report multiple chunks for non-streaming responses.

Note on chunk granularity: kida's ``render_stream`` flushes at expression and
loop boundaries, so an interpolated value (``{{ x }}``) is its own chunk,
separate from the static text around it. Ordering markers below are therefore
pure *static* literals (no embedded interpolation) so each lands intact in one
chunk; interpolated values are checked for presence in the joined text instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chirp import App, AppConfig, Stream, Suspense, Template, TemplateStream
from chirp.testing import CapturedStream, TestClient

# ---------------------------------------------------------------------------
# Fixture templates — deterministic chunk boundaries.
#
# `{% flush %}` is the streaming boundary kida emits between sections. Ordering
# markers (SHELL-HEADER / STATS-SECTION / FEED-SECTION) are static literals so
# they are not split across expression-boundary chunks.
# ---------------------------------------------------------------------------

_STREAM_TEMPLATE = """\
<!DOCTYPE html>
<html><head><title>stream</title></head><body>
<header id="shell-marker">SHELL-HEADER</header>
{% flush %}
<section id="stats-marker">STATS-SECTION
{% for s in stats %}<span>stat:{{ s }}</span>{% end %}
</section>
{% flush %}
<footer id="feed-marker">FEED-SECTION
{% for f in feed %}<div>feed:{{ f }}</div>{% end %}
</footer>
</body></html>"""

_TEMPLATE_STREAM_TEMPLATE = """\
<!DOCTYPE html>
<html><head><title>tstream</title></head><body>
<header id="shell-marker">SHELL-HEADER</header>
{% flush %}
<ul id="items-marker">ITEMS-SECTION
{% async for item in stream %}<li>item:{{ item }}</li>
{% end %}
</ul>
</body></html>"""

_SUSPENSE_TEMPLATE = """\
<!DOCTYPE html>
<html><head><title>suspense</title></head><body>
<header id="shell-marker">SHELL-HEADER</header>
<div id="stats">
{% block stats %}
  {% if stats is deferred %}<span class="skeleton">SKELETON-STATS</span>
  {% else %}<span>LOADED-STATS:{{ stats }}</span>{% end %}
{% end %}
</div>
<div id="feed">
{% block feed %}
  {% if feed is deferred %}<span class="skeleton">SKELETON-FEED</span>
  {% else %}<span>LOADED-FEED:{{ feed }}</span>{% end %}
{% end %}
</div>
</body></html>"""

_BUFFERED_TEMPLATE = """\
<!DOCTYPE html>
<html><head><title>buffered</title></head><body>
<header id="shell-marker">SHELL-HEADER</header>
<p>BUFFERED-BODY</p>
</body></html>"""


def _write_templates(tmp_path: Path) -> Path:
    tdir = tmp_path / "templates"
    tdir.mkdir()
    (tdir / "stream.html").write_text(_STREAM_TEMPLATE)
    (tdir / "tstream.html").write_text(_TEMPLATE_STREAM_TEMPLATE)
    (tdir / "suspense.html").write_text(_SUSPENSE_TEMPLATE)
    (tdir / "buffered.html").write_text(_BUFFERED_TEMPLATE)
    return tdir


def _make_app(tmp_path: Path) -> App:
    """Build an async-worker app whose routes exercise each streaming type."""
    tdir = _write_templates(tmp_path)
    app = App(config=AppConfig(template_dir=tdir, worker_mode="async"))

    async def _load_stats() -> str:
        return "S"

    async def _load_feed() -> str:
        return "F"

    @app.route("/stream")
    async def stream():
        # All data resolves up front; the template's `{% flush %}` boundaries
        # drive the chunk framing (shell, then stats, then feed).
        return Stream("stream.html", stats=["a", "b"], feed=["x", "y"])

    async def _items():
        for i in ("1", "2", "3"):
            yield i

    @app.route("/tstream")
    async def tstream():
        return TemplateStream("tstream.html", stream=_items())

    @app.route("/suspense")
    def suspense():
        # `_load_*` are awaitables -> deferred. Shell renders first with the
        # DEFERRED sentinel, then one OOB chunk per resolved block.
        return Suspense("suspense.html", stats=_load_stats(), feed=_load_feed())

    @app.route("/buffered")
    def buffered():
        # Plain full-page render — single buffered body message.
        return Template("buffered.html")

    return app


# ---------------------------------------------------------------------------
# Stream
# ---------------------------------------------------------------------------


async def test_stream_arrives_in_multiple_chunks(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    async with TestClient(app) as client:
        captured = await client.get_chunks("/stream")

    assert captured.status == 200
    assert captured.streaming is True, "Stream must be sent as a streaming body"
    # A regression that buffers the whole render into one chunk fails here.
    assert captured.chunk_count > 1, (
        f"expected >1 chunk for Stream, got {captured.chunk_count}: {captured.chunks!r}"
    )


async def test_stream_shell_precedes_body(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    async with TestClient(app) as client:
        captured = await client.get_chunks("/stream")

    # Ordering across the flush boundaries: shell, then stats, then feed.
    assert captured.index_of("SHELL-HEADER") < captured.index_of("STATS-SECTION")
    assert captured.index_of("STATS-SECTION") < captured.index_of("FEED-SECTION")
    # All interpolated content is still present once joined.
    text = captured.text
    assert "stat:a" in text
    assert "stat:b" in text
    assert "feed:x" in text
    assert "feed:y" in text


async def test_stream_markers_land_in_expected_chunk(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    async with TestClient(app) as client:
        captured = await client.get_chunks("/stream")

    # The shell marker is in the first chunk (the flush boundary follows it).
    assert "SHELL-HEADER" in captured.chunks[0]
    # The feed section is not smuggled into the shell chunk — it is past two
    # flush boundaries.
    assert "FEED-SECTION" not in captured.chunks[0]
    # And the stats section is likewise not in the shell chunk.
    assert "STATS-SECTION" not in captured.chunks[0]


# ---------------------------------------------------------------------------
# TemplateStream
# ---------------------------------------------------------------------------


async def test_template_stream_multiple_chunks_and_order(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    async with TestClient(app) as client:
        captured = await client.get_chunks("/tstream")

    assert captured.streaming is True
    assert captured.chunk_count > 1, (
        f"expected >1 chunk for TemplateStream, got {captured.chunk_count}: {captured.chunks!r}"
    )
    # Shell header precedes the async-for items section.
    assert captured.index_of("SHELL-HEADER") < captured.index_of("ITEMS-SECTION")
    # The shell chunk does not already contain the streamed items section.
    assert "ITEMS-SECTION" not in captured.chunks[0]
    # All items present once joined, in iterator order.
    text = captured.text
    assert text.index("item:1") < text.index("item:2") < text.index("item:3")


# ---------------------------------------------------------------------------
# Suspense
# ---------------------------------------------------------------------------


async def test_suspense_shell_first_then_deferred_blocks(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    async with TestClient(app) as client:
        captured = await client.get_chunks("/suspense")

    assert captured.status == 200
    assert captured.streaming is True, "Suspense must be sent as a streaming body"
    # Shell + at least one deferred block chunk => more than one chunk.
    assert captured.chunk_count > 1, (
        f"expected >1 chunk for Suspense, got {captured.chunk_count}: {captured.chunks!r}"
    )


async def test_suspense_shell_bytes_precede_loaded_block_bytes(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    async with TestClient(app) as client:
        captured = await client.get_chunks("/suspense")

    # The shell chunk carries the skeletons; the loaded values arrive later.
    shell_idx = captured.index_of("SHELL-HEADER")
    assert "SKELETON-STATS" in captured.chunks[shell_idx], (
        "shell chunk should render the deferred skeleton, not the resolved value"
    )
    assert "LOADED-STATS:S" not in captured.chunks[shell_idx], (
        "resolved stats must not be in the shell chunk — that would mean no deferral"
    )
    # Ordering: shell before each loaded block.
    assert captured.index_of("SHELL-HEADER") < captured.index_of("LOADED-STATS:S")
    assert captured.index_of("SHELL-HEADER") < captured.index_of("LOADED-FEED:F")


async def test_suspense_loaded_markers_land_in_deferred_chunks(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    async with TestClient(app) as client:
        captured = await client.get_chunks("/suspense")

    # Both resolved values arrive (in deferred OOB chunks after the shell).
    assert "LOADED-STATS:S" in captured.text
    assert "LOADED-FEED:F" in captured.text
    # The loaded markers are not in the very first (shell) chunk.
    assert "LOADED-STATS:S" not in captured.chunks[0]
    assert "LOADED-FEED:F" not in captured.chunks[0]


# ---------------------------------------------------------------------------
# Control: buffered Response must NOT report streaming framing.
# ---------------------------------------------------------------------------


async def test_buffered_response_is_single_chunk(tmp_path: Path) -> None:
    """Guards against the helper vacuously reporting multiple chunks.

    If a buffered full-page render reported >1 chunk or ``streaming=True``, the
    streaming assertions above would pass for the wrong reason.
    """
    app = _make_app(tmp_path)
    async with TestClient(app) as client:
        captured = await client.get_chunks("/buffered")

    assert captured.status == 200
    assert captured.streaming is False, "a buffered Response must not use more_body"
    assert captured.chunk_count == 1, (
        f"buffered Response should be one chunk, got {captured.chunk_count}: {captured.chunks!r}"
    )
    assert "SHELL-HEADER" in captured.text
    assert "BUFFERED-BODY" in captured.text


# ---------------------------------------------------------------------------
# CapturedStream API surface / backward-compat.
# ---------------------------------------------------------------------------


async def test_index_of_raises_for_missing_marker(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    async with TestClient(app) as client:
        captured = await client.get_chunks("/buffered")

    with pytest.raises(AssertionError):
        captured.index_of("NOPE-NOT-PRESENT")


async def test_request_chunks_matches_buffered_request_body(tmp_path: Path) -> None:
    """The joined chunk text equals the buffered Response body (no surface break)."""
    app = _make_app(tmp_path)
    async with TestClient(app) as client:
        buffered = await client.get("/stream")
        captured = await client.get_chunks("/stream")

    assert isinstance(captured, CapturedStream)
    assert captured.text == buffered.text
