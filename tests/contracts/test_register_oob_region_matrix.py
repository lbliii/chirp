"""Contract tests for ``register_oob_region()`` — full registration matrix.

Sprint 2 of docs/plan-contract-tests-reliability.md. Covers every swap type
the registry accepts, plus the three registration error / edge cases:
invalid swap value, freeze guard, and duplicate-registration semantics.

Companion to ``test_oob_pipeline_e2e.py`` (Sprint 1) which covers the
request → render → response flow. This module focuses on the registration
API surface itself — what the registry accepts and rejects, and what the
serialization config looks like in the response when each option is used.
"""

from __future__ import annotations

import pytest

from chirp.templating.returns import OOB, Fragment
from chirp.testing import TestClient
from tests.contracts._helpers import _app

# ---------------------------------------------------------------------------
# 2.1 — Parametrized swap-type matrix
# ---------------------------------------------------------------------------

# All six htmx swap strategies the OOB registry accepts. ``true`` is the
# htmx alias for ``outerHTML`` and is therefore the convention default.
_SWAP_VARIANTS = [
    "innerHTML",
    "true",
    "beforeend",
    "afterend",
    "beforebegin",
    "afterbegin",
]


class TestSwapTypeMatrix:
    """Every swap variant flows through the registry to the response body.

    Locks in that ``register_oob_region(..., swap=X)`` causes the rendered
    OOB wrapper to carry ``hx-swap-oob="X"`` — i.e. there is no silent
    coercion, default-substitution, or per-strategy renderer fork.
    """

    @pytest.mark.parametrize("swap", _SWAP_VARIANTS)
    async def test_registered_swap_appears_in_response(self, swap: str) -> None:
        app = _app()
        app.register_oob_region(
            "breadcrumbs_oob",
            target_id="breadcrumbs",
            swap=swap,
            wrap=True,
        )

        @app.route("/")
        def index():
            return OOB(
                Fragment("fragments.html", "article", heading="A", body="B"),
                Fragment(
                    "fragments.html",
                    "breadcrumbs_oob",
                    target="breadcrumbs",
                    crumbs="X",
                ),
            )

        async with TestClient(app) as client:
            response = await client.get("/", headers={"HX-Request": "true"})

        assert response.status == 200, (
            f"swap={swap!r} produced status {response.status}: {response.text[:200]}"
        )
        body = response.text
        assert 'id="breadcrumbs"' in body, f"swap={swap!r}: no wrapper id in body"
        assert f'hx-swap-oob="{swap}"' in body, (
            f"swap={swap!r}: expected hx-swap-oob={swap!r} in body, got: {body[:300]}"
        )


# ---------------------------------------------------------------------------
# 2.2 — Invalid swap rejected at registration time
# ---------------------------------------------------------------------------


class TestInvalidSwapRejected:
    """``register_oob_region(swap=<unknown>)`` raises ValueError naming the value.

    Validation happens in ``OOBRegionConfig.__post_init__`` →
    ``_validate_swap`` (src/chirp/templating/returns.py:46), so the failure
    occurs at registration, not at render time. This protects against typos
    silently shipping ("inner_html", "beforend", etc.) and being noticed only
    when a user sees a broken swap in production.
    """

    def test_unknown_swap_value_raises_value_error(self) -> None:
        app = _app()
        # match= asserts the error names the offending value — protects
        # against a future swallow-and-wrap that hides the original input.
        with pytest.raises(ValueError, match="garbage"):
            app.register_oob_region(
                "breadcrumbs_oob",
                target_id="breadcrumbs",
                swap="garbage",
            )

    def test_empty_swap_value_raises_value_error(self) -> None:
        app = _app()
        with pytest.raises(ValueError, match=r"(?i)empty|whitespace"):
            app.register_oob_region(
                "breadcrumbs_oob",
                target_id="breadcrumbs",
                swap="   ",
            )


# ---------------------------------------------------------------------------
# 2.3 — Freeze guard: cannot register after app.freeze()
# ---------------------------------------------------------------------------


class TestFreezeGuard:
    """OOB registry follows the same freeze lifecycle as routes/middleware.

    Once the app is frozen (manually via ``app.freeze()`` or implicitly when
    serving the first request), registration must raise — silent acceptance
    of post-freeze writes would create a race window where some requests see
    the new region and others do not.
    """

    def test_register_after_freeze_raises_runtime_error(self) -> None:
        app = _app()
        app.register_oob_region(
            "breadcrumbs_oob",
            target_id="breadcrumbs",
            swap="innerHTML",
        )
        app.freeze()

        with pytest.raises(RuntimeError) as exc_info:
            app.register_oob_region(
                "sidebar_oob",
                target_id="sidebar-nav",
                swap="innerHTML",
            )
        # The message should communicate the lifecycle violation, not just
        # surface a generic AttributeError or KeyError.
        msg = str(exc_info.value).lower()
        assert "frozen" in msg or "started" in msg or "after" in msg, (
            f"freeze-guard error message should describe the lifecycle, got: {msg}"
        )


# ---------------------------------------------------------------------------
# 2.4 — Duplicate registration silently overwrites
# ---------------------------------------------------------------------------


class TestDuplicateRegistration:
    """Re-registering the same block name silently overwrites the prior config.

    Documents the **current** behavior at
    ``src/chirp/templating/oob_registry.py:54`` — ``self._regions[block_name]
    = config`` is unconditional. If product intent later changes to "reject
    duplicates", this test will fail and surface that intent before a silent
    behavior change ships.
    """

    async def test_second_registration_overwrites_first(self) -> None:
        app = _app()
        # First registration — innerHTML
        app.register_oob_region(
            "breadcrumbs_oob",
            target_id="breadcrumbs",
            swap="innerHTML",
            wrap=True,
        )
        # Second registration — different swap and target_id
        app.register_oob_region(
            "breadcrumbs_oob",
            target_id="new-breadcrumbs",
            swap="beforeend",
            wrap=True,
        )

        @app.route("/")
        def index():
            return OOB(
                Fragment("fragments.html", "article", heading="A", body="B"),
                Fragment(
                    "fragments.html",
                    "breadcrumbs_oob",
                    target="new-breadcrumbs",
                    crumbs="X",
                ),
            )

        async with TestClient(app) as client:
            response = await client.get("/", headers={"HX-Request": "true"})

        body = response.text
        # The second registration's config wins.
        assert 'id="new-breadcrumbs"' in body
        assert 'hx-swap-oob="beforeend"' in body
        # The first registration's target is gone — not co-existing.
        assert 'id="breadcrumbs"' not in body
