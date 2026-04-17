"""Contract tests for ``MutationResult`` end-to-end with the OOB registry.

Sprint 3 of docs/plan-contract-tests-reliability.md. Covers the
registry-aware path through ``MutationResult`` (alias: ``FormAction``):

- htmx POST + fragments → primary swap + OOB-wrapped secondaries
  whose swap strategy comes from the registry (not the default ``true``).
- htmx POST + no fragments → ``HX-Redirect`` header.
- non-htmx POST → 303 ``Location``.
- ``trigger=...`` → ``HX-Trigger`` response header.
- Explicit ``Fragment(..., swap=...)`` wins over the registry config.

Companion to ``tests/test_form_action.py`` which covers the htmx /
non-htmx branching but **never wires up the OOB registry** — every secondary
fragment in that suite falls through ``swap_attr is None and oob_registry is
None`` and gets the default ``"true"``. This module fills that gap.
"""

from __future__ import annotations

from chirp.templating.returns import Fragment, MutationResult
from chirp.testing import TestClient
from tests.contracts._helpers import _app


def _header(response, name: str) -> str | None:
    """Look up a single response header by name (case-insensitive — ASGI lowercases)."""
    target = name.lower()
    for hname, hvalue in response.headers:
        if hname.lower() == target:
            return hvalue
    return None


# ---------------------------------------------------------------------------
# 3.1 — htmx POST + fragments resolve via registry
# ---------------------------------------------------------------------------


class TestMutationResultRegistryAwareFragments:
    """Secondary fragments under ``MutationResult`` use the registry's swap.

    Locks in the integration at ``src/chirp/server/negotiation.py:261`` —
    ``oob_registry.resolve_serialization(target_id)`` is consulted for every
    fragment beyond the primary. Without this test, a regression that drops
    the registry lookup would pass the existing ``tests/test_form_action.py``
    suite (which never registers a region).
    """

    async def test_secondary_fragment_uses_registered_swap(self) -> None:
        """Registered swap='innerHTML' beats default 'true' for secondary fragments."""
        app = _app()
        app.register_oob_region(
            "breadcrumbs_oob",
            target_id="breadcrumbs",
            swap="innerHTML",
        )

        @app.route("/save", methods=["POST"])
        def save():
            return MutationResult(
                "/done",
                # Primary swap — first fragment gets no OOB wrapper.
                Fragment("fragments.html", "article", heading="A", body="B"),
                # Secondary — must look up "breadcrumbs" in the registry.
                Fragment(
                    "fragments.html",
                    "breadcrumbs_oob",
                    target="breadcrumbs",
                    crumbs="X",
                ),
            )

        async with TestClient(app) as client:
            response = await client.post(
                "/save", headers={"HX-Request": "true"}
            )

        assert response.status == 200
        body = response.text
        # Primary fragment present, no OOB wrapper around it.
        assert "<article" in body
        # Secondary fragment is wrapped per registry config.
        assert 'id="breadcrumbs"' in body
        assert 'hx-swap-oob="innerHTML"' in body
        # The default that would appear if registry lookup were skipped.
        assert 'hx-swap-oob="true"' not in body

    async def test_secondary_fragment_default_swap_when_unregistered(self) -> None:
        """Without a registry entry, secondary fragments fall back to swap='true'."""
        app = _app()
        # No register_oob_region — exercises the convention default at
        # oob_registry.py:78 (``return "true", True``).

        @app.route("/save", methods=["POST"])
        def save():
            return MutationResult(
                "/done",
                Fragment("fragments.html", "article", heading="A", body="B"),
                Fragment(
                    "fragments.html",
                    "sidebar_oob",
                    target="sidebar-nav",
                    link="L",
                ),
            )

        async with TestClient(app) as client:
            response = await client.post(
                "/save", headers={"HX-Request": "true"}
            )

        body = response.text
        assert 'id="sidebar-nav"' in body
        assert 'hx-swap-oob="true"' in body


# ---------------------------------------------------------------------------
# 3.2 — htmx POST + no fragments → HX-Redirect header
# ---------------------------------------------------------------------------


class TestMutationResultHtmxRedirect:
    """htmx POST without fragments returns an empty body + HX-Redirect."""

    async def test_htmx_no_fragments_sends_hx_redirect(self) -> None:
        app = _app()

        @app.route("/save", methods=["POST"])
        def save():
            return MutationResult("/thanks")

        async with TestClient(app) as client:
            response = await client.post(
                "/save", headers={"HX-Request": "true"}
            )

        assert response.status == 200
        assert _header(response, "HX-Redirect") == "/thanks"
        # Per spec: htmx no-fragments path uses HX-Redirect, NOT Location.
        assert _header(response, "location") is None
        assert _header(response, "Location") is None


# ---------------------------------------------------------------------------
# 3.3 — non-htmx POST → 303 Location
# ---------------------------------------------------------------------------


class TestMutationResultNonHtmxRedirect:
    """Plain (non-htmx) POST falls through to a standard 303 redirect."""

    async def test_non_htmx_returns_303_with_location(self) -> None:
        app = _app()

        @app.route("/save", methods=["POST"])
        def save():
            return MutationResult("/thanks")

        async with TestClient(app) as client:
            response = await client.post("/save")

        assert response.status == 303
        assert _header(response, "location") == "/thanks"
        # And no htmx-specific headers leak into the non-htmx path.
        assert _header(response, "HX-Redirect") is None

    async def test_non_htmx_ignores_fragments(self) -> None:
        """Even when fragments are provided, non-htmx still gets the 303."""
        app = _app()

        @app.route("/save", methods=["POST"])
        def save():
            return MutationResult(
                "/thanks",
                Fragment("fragments.html", "article", heading="A", body="B"),
            )

        async with TestClient(app) as client:
            response = await client.post("/save")

        assert response.status == 303
        assert _header(response, "location") == "/thanks"


# ---------------------------------------------------------------------------
# 3.4 — HX-Trigger header
# ---------------------------------------------------------------------------


class TestMutationResultHxTrigger:
    """``trigger=...`` adds the HX-Trigger header to the htmx response."""

    async def test_trigger_kwarg_sets_hx_trigger_header(self) -> None:
        app = _app()

        @app.route("/save", methods=["POST"])
        def save():
            return MutationResult(
                "/done",
                Fragment("fragments.html", "article", heading="A", body="B"),
                trigger="contactSaved",
            )

        async with TestClient(app) as client:
            response = await client.post(
                "/save", headers={"HX-Request": "true"}
            )

        assert response.status == 200
        assert _header(response, "HX-Trigger") == "contactSaved"

    async def test_no_trigger_means_no_header(self) -> None:
        app = _app()

        @app.route("/save", methods=["POST"])
        def save():
            return MutationResult(
                "/done",
                Fragment("fragments.html", "article", heading="A", body="B"),
            )

        async with TestClient(app) as client:
            response = await client.post(
                "/save", headers={"HX-Request": "true"}
            )

        assert _header(response, "HX-Trigger") is None


# ---------------------------------------------------------------------------
# 3.5 — Explicit Fragment.swap overrides registry
# ---------------------------------------------------------------------------


class TestExplicitFragmentSwapOverridesRegistry:
    """``Fragment(..., swap=X)`` beats ``register_oob_region(swap=Y)``.

    The negotiation layer at ``negotiation.py:260`` checks ``getattr(frag,
    "swap", None)`` first; only ``None`` falls through to the registry. This
    lets a route opt out of the registered default for one specific call site
    without touching app setup.
    """

    async def test_explicit_swap_wins_over_registered_swap(self) -> None:
        app = _app()
        # Registry says innerHTML for this region.
        app.register_oob_region(
            "breadcrumbs_oob",
            target_id="breadcrumbs",
            swap="innerHTML",
        )

        @app.route("/save", methods=["POST"])
        def save():
            return MutationResult(
                "/done",
                Fragment("fragments.html", "article", heading="A", body="B"),
                # Explicit swap=beforeend on the call site — must win.
                Fragment(
                    "fragments.html",
                    "breadcrumbs_oob",
                    target="breadcrumbs",
                    swap="beforeend",
                    crumbs="X",
                ),
            )

        async with TestClient(app) as client:
            response = await client.post(
                "/save", headers={"HX-Request": "true"}
            )

        body = response.text
        assert 'id="breadcrumbs"' in body
        assert 'hx-swap-oob="beforeend"' in body
        # The registered default must NOT appear for this fragment.
        assert 'hx-swap-oob="innerHTML"' not in body
