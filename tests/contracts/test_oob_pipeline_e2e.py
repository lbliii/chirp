"""End-to-end contract tests for the OOB pipeline.

Drives every public surface of ``register_oob_region()`` + ``OOB(...)`` through
``TestClient`` so the request → registry → render → response contract is
verified at the HTTP layer (not just the renderer/serializer level covered by
``tests/test_oob_registry.py`` and ``tests/test_render_plan_fail_loud.py``).

Sprint 1 of docs/plan-contract-tests-reliability.md.
"""

from __future__ import annotations

import logging

import pytest

from chirp import App
from chirp.templating.returns import OOB, Fragment, Template
from chirp.testing import TestClient
from tests.contracts._helpers import _app

# ---------------------------------------------------------------------------
# 1.1 — Happy path: register region, return OOB(...), assert response markup
# ---------------------------------------------------------------------------


class TestOOBHappyPath:
    """Registered regions drive swap/wrap on OOB() return values."""

    async def test_oob_response_contains_registered_swap_and_wrap(self) -> None:
        """register_oob_region(swap='innerHTML', wrap=True) → wrapper div in body."""
        app = _app()
        app.register_oob_region(
            "breadcrumbs_oob",
            target_id="breadcrumbs",
            swap="innerHTML",
            wrap=True,
        )

        @app.route("/")
        def index():
            return OOB(
                Fragment("fragments.html", "article", heading="Hi", body="hello"),
                Fragment("fragments.html", "breadcrumbs_oob", target="breadcrumbs", crumbs="Home > Page"),
            )

        async with TestClient(app) as client:
            response = await client.get("/", headers={"HX-Request": "true"})

        assert response.status == 200
        body = response.text
        # Main fragment rendered first
        assert "hello" in body
        # OOB fragment is wrapped with the registry-configured swap strategy
        assert 'id="breadcrumbs"' in body
        assert 'hx-swap-oob="innerHTML"' in body
        # Default ("true"/outerHTML) must NOT be used when registry says innerHTML
        assert 'id="breadcrumbs" hx-swap-oob="true"' not in body

    async def test_oob_response_renders_main_and_secondary_fragments(self) -> None:
        """Multiple OOB fragments all appear in the same response body."""
        app = _app()
        app.register_oob_region("breadcrumbs_oob", target_id="breadcrumbs", swap="innerHTML")
        app.register_oob_region("notif_feed_oob", target_id="notif-feed", swap="beforeend")

        @app.route("/")
        def index():
            return OOB(
                Fragment("fragments.html", "article", heading="A", body="B"),
                Fragment("fragments.html", "breadcrumbs_oob", target="breadcrumbs", crumbs="X"),
                Fragment("fragments.html", "notif_feed_oob", target="notif-feed", notif="N"),
            )

        async with TestClient(app) as client:
            response = await client.get("/", headers={"HX-Request": "true"})

        body = response.text
        assert 'id="breadcrumbs"' in body
        assert 'hx-swap-oob="innerHTML"' in body
        assert 'id="notif-feed"' in body
        assert 'hx-swap-oob="beforeend"' in body


# ---------------------------------------------------------------------------
# 1.2 — Convention fallback: unregistered block name → default swap/wrap
# ---------------------------------------------------------------------------


class TestOOBConventionFallback:
    """Unregistered OOB block names fall back to outerHTML + wrap."""

    async def test_unregistered_block_uses_default_swap_and_wrap(self) -> None:
        """No register_oob_region — defaults from resolve_serialization apply."""
        app = _app()

        @app.route("/")
        def index():
            return OOB(
                Fragment("fragments.html", "article", heading="A", body="B"),
                # No registry entry; target derived from block_name
                Fragment("fragments.html", "sidebar_oob", target="sidebar-nav", link="L"),
            )

        async with TestClient(app) as client:
            response = await client.get("/", headers={"HX-Request": "true"})

        body = response.text
        # Default swap is "true" (outerHTML); wrap=True wraps in <div id=...>
        assert 'id="sidebar-nav"' in body
        assert 'hx-swap-oob="true"' in body


# ---------------------------------------------------------------------------
# 1.3 — Explicit target_id and wrap=False
# ---------------------------------------------------------------------------


class TestOOBExplicitTargetAndWrap:
    """target_id overrides the block name; wrap=False emits raw block markup."""

    async def test_explicit_target_id_used_in_oob_swap(self) -> None:
        """register_oob_region(target_id='custom') wraps with that ID."""
        app = _app()
        app.register_oob_region(
            "breadcrumbs_oob",
            target_id="custom-breadcrumb-region",
            swap="innerHTML",
        )

        @app.route("/")
        def index():
            return OOB(
                Fragment("fragments.html", "article", heading="A", body="B"),
                Fragment(
                    "fragments.html",
                    "breadcrumbs_oob",
                    target="custom-breadcrumb-region",
                    crumbs="X",
                ),
            )

        async with TestClient(app) as client:
            response = await client.get("/", headers={"HX-Request": "true"})

        body = response.text
        assert 'id="custom-breadcrumb-region"' in body
        assert 'hx-swap-oob="innerHTML"' in body

    async def test_wrap_false_emits_block_markup_without_wrapper_div(self) -> None:
        """wrap=False is for blocks that self-include hx-swap-oob (e.g. <title>)."""
        app = _app()
        app.register_oob_region(
            "title_oob",
            target_id="page-title",
            swap="true",
            wrap=False,
        )

        @app.route("/")
        def index():
            return OOB(
                Fragment("fragments.html", "article", heading="A", body="B"),
                Fragment("fragments.html", "title_oob", target="page-title", page_title="Hello"),
            )

        async with TestClient(app) as client:
            response = await client.get("/", headers={"HX-Request": "true"})

        body = response.text
        # The <title> element from the block carries hx-swap-oob itself
        assert "<title" in body
        assert 'id="page-title"' in body
        assert 'hx-swap-oob="true"' in body
        # No wrapper div: the block markup appears un-wrapped (no extra <div id="page-title">)
        assert '<div id="page-title"' not in body


# ---------------------------------------------------------------------------
# 1.4 — optional=True silent-skip when layout omits the block
# ---------------------------------------------------------------------------


class TestOOBOptionalSilentSkip:
    """optional=True regions are silently skipped when the layout omits them.

    Drives the layout-region path (boosted navigation): when an optional region
    is registered but the rendered layout has no matching block, the response
    must not include an empty OOB wrapper div (which would wipe live DOM).
    """

    async def test_optional_missing_block_not_in_response(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        from pathlib import Path

        # Use the minimal layout that intentionally omits all OOB regions.
        templates = Path(__file__).parent / "templates" / "oob_e2e"
        app = _app(template_dir=templates)
        app.register_oob_region(
            "breadcrumbs_oob",
            target_id="breadcrumbs",
            swap="innerHTML",
            optional=True,
        )

        @app.route("/")
        def index():
            # Page extends _layout.html (which DOES define breadcrumbs_oob),
            # so we use _layout_minimal.html via an inline template.
            return Template("_layout_minimal.html")

        with caplog.at_level(logging.WARNING):
            async with TestClient(app) as client:
                response = await client.get("/")

        assert response.status == 200
        body = response.text
        # Optional region's target must NOT appear as a wrapper div
        assert '<div id="breadcrumbs" hx-swap-oob' not in body


# ---------------------------------------------------------------------------
# 1.5 — Regression replay: PR #90 (fail-loud on missing block)
# ---------------------------------------------------------------------------


class TestPR90RegressionReplay:
    """PR #90 (fd53ff8): missing OOB blocks must fail loud — never emit an
    empty hx-swap-oob wrapper that would silently wipe client DOM content.

    Two distinct paths:
    - ``OOB(Fragment(...))`` with a missing block: kida raises KeyError, the
      handler returns 500 (the request fails loudly, no empty 200 success).
    - Layout region updates (boosted navigation): execute_render_plan wraps
      the missing block in BlockNotFoundError. Covered at the render-plan
      level by tests/test_render_plan_fail_loud.py; this suite verifies the
      HTTP-layer outcome (500, not 200 with empty swaps).
    """

    async def test_oob_with_missing_block_fails_loud_pr90(self) -> None:
        """OOB() referencing a non-existent block returns 500, not silent 200."""
        app = _app()

        @app.route("/")
        def index():
            return OOB(
                Fragment("fragments.html", "article", heading="A", body="B"),
                # block "ghost_oob" does NOT exist in fragments.html
                Fragment("fragments.html", "ghost_oob", target="ghost-region"),
            )

        async with TestClient(app) as client:
            response = await client.get("/", headers={"HX-Request": "true"})

        # Fail loud: 500, not a 200 with an empty <div id="ghost-region" hx-swap-oob>
        assert response.status == 500
        # And the response body must NOT contain a wrapper div for the missing
        # region (the regression that PR #90 closed: empty wrappers wiping DOM).
        assert '<div id="ghost-region" hx-swap-oob' not in response.text

    async def test_oob_missing_block_does_not_emit_empty_wrapper_pr90(self) -> None:
        """Even with multiple OOB fragments, a missing one must not silently
        emit an empty <div id=... hx-swap-oob> alongside the successful ones."""
        app = _app()
        app.register_oob_region("breadcrumbs_oob", target_id="breadcrumbs", swap="innerHTML")

        @app.route("/")
        def index():
            return OOB(
                Fragment("fragments.html", "article", heading="A", body="B"),
                Fragment("fragments.html", "breadcrumbs_oob", target="breadcrumbs", crumbs="X"),
                Fragment("fragments.html", "phantom_oob", target="phantom-region"),
            )

        async with TestClient(app) as client:
            response = await client.get("/", headers={"HX-Request": "true"})

        # Fail loud — entire response is 500, not a 200 with the good fragment
        # plus a silently-empty wrapper for the missing one.
        assert response.status == 500
        assert '<div id="phantom-region" hx-swap-oob' not in response.text


# ---------------------------------------------------------------------------
# 1.6 — Regression replay: PR #87 (startup validation of OOB registry)
# ---------------------------------------------------------------------------


def _pages_mounted_app(tmp_path) -> App:
    """Build a minimal pages-mounted app so check_oob_registry_coverage has a
    layout chain to inspect (the production wiring at checker.py:462-474 only
    fires when ``snapshot.layout_chains`` is non-empty)."""
    from chirp import AppConfig

    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "_layout.html").write_text(
        "<!doctype html><html><body><main id='main'>"
        "{% block content %}{% end %}"
        "</main></body></html>",
        encoding="utf-8",
    )
    (pages_dir / "page.py").write_text(
        "from chirp import Page\n"
        "def handler() -> Page:\n"
        "    return Page('page.html', 'content')\n",
        encoding="utf-8",
    )
    (pages_dir / "page.html").write_text(
        "{% block content %}<h1>Index</h1>{% end %}",
        encoding="utf-8",
    )
    app = App(AppConfig(template_dir=str(pages_dir)))
    app.mount_pages(str(pages_dir))
    return app


class TestPR87RegressionReplay:
    """PR #87 (4e888da): startup validation must flag OOB registrations whose
    blocks do not exist in any layout template — ERROR for required, WARNING
    for optional.

    These tests exercise the production wiring at
    ``checker.py:462`` (snapshot.layout_chains → check_oob_registry_coverage).
    Function-level coverage of ``check_oob_registry_coverage`` itself lives in
    ``tests/test_render_plan_fail_loud.py::TestOrphanOOBSeverity``; this suite
    proves the wiring is intact end-to-end via a pages-mounted app.
    """

    def test_orphaned_oob_registration_flagged_at_startup_pr87(
        self, tmp_path
    ) -> None:
        """Required orphan → ERROR-severity issue under category oob_registry."""
        from chirp.contracts.checker import check_hypermedia_surface
        from chirp.contracts.types import Severity

        app = _pages_mounted_app(tmp_path)
        app.register_oob_region(
            "phantom_oob",
            target_id="phantom-region",
            swap="innerHTML",
            optional=False,
        )

        result = check_hypermedia_surface(app)
        oob_issues = [i for i in result.issues if i.category == "oob_registry"]
        matching = [i for i in oob_issues if "phantom_oob" in i.message]
        assert matching, (
            f"Expected an oob_registry issue mentioning 'phantom_oob'.\n"
            f"All issues: {[(i.category, i.severity, i.message[:80]) for i in result.issues]}"
        )
        assert all(i.severity is Severity.ERROR for i in matching), (
            f"Required orphan must be ERROR severity, got: "
            f"{[i.severity for i in matching]}"
        )

    def test_optional_orphan_downgraded_to_warning_pr87(self, tmp_path) -> None:
        """Optional orphan → WARNING (not ERROR)."""
        from chirp.contracts.checker import check_hypermedia_surface
        from chirp.contracts.types import Severity

        app = _pages_mounted_app(tmp_path)
        app.register_oob_region(
            "ghost_optional_oob",
            target_id="ghost-optional",
            swap="innerHTML",
            optional=True,
        )

        result = check_hypermedia_surface(app)
        oob_issues = [i for i in result.issues if i.category == "oob_registry"]
        matching = [i for i in oob_issues if "ghost_optional_oob" in i.message]
        assert matching, "Expected an oob_registry issue for the optional orphan"
        assert all(i.severity is Severity.WARNING for i in matching), (
            f"Optional orphan must be WARNING severity, got: "
            f"{[i.severity for i in matching]}"
        )
