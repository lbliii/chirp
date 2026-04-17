"""End-to-end contract tests for ``AppConfig.speculation_rules`` injection.

Sprint 5 of docs/plan-contract-tests-reliability.md. The unit suite at
``tests/test_speculation_rules.py`` covers the JSON builder and snippet
wrapper exhaustively, but **never confirms the snippet actually lands in
the rendered ``<head>``** of a real response. This module fills that gap.

Coverage:

- 5.1 — snippet present when enabled
- 5.2 — snippet absent when disabled
- 5.3 — three modes (conservative/moderate/eager) produce mode-specific JSON
- 5.4 — POST and SSE routes excluded from the URL list
- 5.5 — fragment (boosted) responses do NOT receive the snippet
        (HTMLInject is gated by ``full_page_only=True``)
"""

from __future__ import annotations

import json
import re

import pytest

from chirp.realtime.events import EventStream
from chirp.templating.returns import Fragment, Template
from chirp.testing import TestClient
from tests.contracts._helpers import _app

_SCRIPT_TAG_RE = re.compile(
    r'<script[^>]*type="speculationrules"[^>]*data-chirp="speculation-rules"[^>]*>'
    r"(.*?)</script>",
    re.DOTALL,
)


def _extract_speculation_json(body: str) -> dict | None:
    """Return parsed speculation-rules JSON from the response, or None if absent.

    The snippet is HTML-escaped (``<`` → ``\\u003c``, ``&`` → ``\\u0026``)
    before injection, so unescape first to round-trip back to JSON.
    """
    match = _SCRIPT_TAG_RE.search(body)
    if match is None:
        return None
    payload = match.group(1).replace("\\u003c", "<").replace("\\u0026", "&")
    return json.loads(payload)


def _has_speculation_snippet(body: str) -> bool:
    return _SCRIPT_TAG_RE.search(body) is not None


# ---------------------------------------------------------------------------
# 5.1 — Snippet present when enabled
# ---------------------------------------------------------------------------


class TestSnippetPresentWhenEnabled:
    """``speculation_rules=True`` injects the snippet inside ``<head>``."""

    async def test_full_page_response_includes_snippet_in_head(self) -> None:
        app = _app(speculation_rules=True)

        @app.route("/")
        def index():
            return Template("spec_page.html")

        async with TestClient(app) as client:
            response = await client.get("/")

        assert response.status == 200
        body = response.text
        # The snippet itself must be present...
        assert _has_speculation_snippet(body), (
            f"Expected speculation-rules snippet in body. Body: {body[:500]}"
        )
        # ...and it must land BEFORE </head> (HTMLInject contract).
        head_close = body.find("</head>")
        snippet_pos = body.find('type="speculationrules"')
        assert head_close != -1, "no </head> in response"
        assert snippet_pos != -1
        assert snippet_pos < head_close, (
            f"snippet at {snippet_pos} should precede </head> at {head_close}"
        )


# ---------------------------------------------------------------------------
# 5.2 — Snippet absent when disabled
# ---------------------------------------------------------------------------


class TestSnippetAbsentWhenDisabled:
    """``speculation_rules=False`` (the default) emits no snippet."""

    async def test_default_config_emits_no_snippet(self) -> None:
        app = _app()  # speculation_rules defaults to False

        @app.route("/")
        def index():
            return Template("spec_page.html")

        async with TestClient(app) as client:
            response = await client.get("/")

        body = response.text
        assert not _has_speculation_snippet(body)
        assert "speculationrules" not in body
        assert "speculation-rules" not in body


# ---------------------------------------------------------------------------
# 5.3 — Mode parametrization (conservative / moderate / eager)
# ---------------------------------------------------------------------------


class TestModeParametrization:
    """Each mode injects a snippet with mode-specific JSON shape.

    Locks in the per-mode logic at ``speculation_rules.py:85`` (conservative
    only prefetches), ``:98`` (moderate prefetches + prerenders),
    ``:112`` (eager prerenders).
    """

    @pytest.mark.parametrize(
        ("mode", "expected_keys"),
        [
            ("conservative", {"prefetch"}),
            ("moderate", {"prefetch", "prerender"}),
            ("eager", {"prerender"}),
        ],
    )
    async def test_mode_produces_expected_top_level_keys(
        self, mode: str, expected_keys: set[str]
    ) -> None:
        app = _app(speculation_rules=mode)

        @app.route("/")
        def index():
            return Template("spec_page.html")

        @app.route("/about")
        def about():
            return Template("spec_page.html")

        async with TestClient(app) as client:
            response = await client.get("/")

        rules = _extract_speculation_json(response.text)
        assert rules is not None, f"mode={mode!r}: expected snippet in body"
        assert set(rules.keys()) == expected_keys, (
            f"mode={mode!r}: expected keys {expected_keys}, got {set(rules.keys())}"
        )


# ---------------------------------------------------------------------------
# 5.4 — POST and SSE routes excluded from rules
# ---------------------------------------------------------------------------


class TestPostAndSseExcluded:
    """Only static GET routes appear in the rules — POST and SSE never."""

    async def test_post_and_sse_paths_absent_from_url_list(self) -> None:
        app = _app(speculation_rules="moderate")

        @app.route("/about")
        def about_page():
            return Template("spec_page.html")

        @app.route("/save", methods=["POST"])
        def save():
            return Template("spec_page.html")

        async def _gen():
            yield "tick"

        @app.route("/events", referenced=True)
        def events():
            return EventStream(_gen())

        @app.route("/")
        def index():
            return Template("spec_page.html")

        async with TestClient(app) as client:
            response = await client.get("/")

        rules = _extract_speculation_json(response.text)
        assert rules is not None

        # Flatten every URL from every prefetch/prerender block.
        all_urls: list[str] = []
        for blocks in rules.values():
            for block in blocks:
                all_urls.extend(block.get("urls", []))

        assert "/" in all_urls
        assert "/about" in all_urls
        # POST endpoints must not be prefetched/prerendered (would trigger
        # mutations on hover) — and SSE endpoints would open dangling
        # connections from prefetch.
        assert "/save" not in all_urls, f"POST route leaked into rules: {all_urls}"
        assert "/events" not in all_urls, f"SSE route leaked into rules: {all_urls}"


# ---------------------------------------------------------------------------
# 5.5 — Fragment / boosted responses do NOT include the snippet
# ---------------------------------------------------------------------------


class TestSnippetExcludedFromFragmentResponses:
    """``HTMLInject(..., full_page_only=True)`` keeps the snippet off
    htmx fragment responses — only full-page navigations need it.

    Without this guard, every fragment swap would re-inject the snippet
    into the body of the fragment, eventually polluting the live DOM with
    duplicate/stale rule blocks.
    """

    async def test_fragment_response_does_not_include_snippet(self) -> None:
        """A route returning ``Fragment(...)`` renders with intent=fragment;
        ``HTMLInject(full_page_only=True)`` must skip injection."""
        app = _app(speculation_rules=True)

        @app.route("/snippet")
        def snippet_only():
            return Fragment("spec_page.html", "snippet")

        async with TestClient(app) as client:
            response = await client.get("/snippet", headers={"HX-Request": "true"})

        assert response.status == 200
        # Fragment-style responses must not carry the speculation-rules snippet.
        assert not _has_speculation_snippet(response.text), (
            f"Snippet leaked into fragment response: {response.text[:300]}"
        )
        assert "speculationrules" not in response.text
