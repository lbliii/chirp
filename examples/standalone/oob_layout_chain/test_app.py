"""Tests for oob_layout_chain example.

Headline feature: OOB regions are *suppressed* on a full-page render (so they
never emit orphaned ``hx-swap-oob`` fragments into a fresh document), but the
layout chain emits ``hx-swap-oob`` markup on an HTMX shell navigation so the
out-of-band regions can be swapped in place.
"""

from chirp.testing import TestClient


async def test_full_page_renders(example_app) -> None:
    async with TestClient(example_app) as client:
        response = await client.get("/")
        assert response.status == 200
        assert "Welcome to the OOB layout chain example" in response.text
        assert 'id="main"' in response.text


async def test_fragment_request(example_app) -> None:
    async with TestClient(example_app) as client:
        response = await client.fragment("/")
        assert response.status == 200
        assert "Welcome" in response.text or "card" in response.text


async def test_full_page_suppresses_oob(example_app) -> None:
    """A full-page document must not carry ``hx-swap-oob`` markup.

    Emitting an OOB swap into a freshly loaded document would target a DOM id
    that does not yet exist, so the region is suppressed on full-page render.
    The sidebar region body is likewise not painted inline.
    """
    async with TestClient(example_app) as client:
        response = await client.get("/")
        assert response.status == 200
        assert "hx-swap-oob" not in response.text
        # The {% region sidebar_oob %} body is suppressed on full-page.
        assert "sidebar" not in response.text


async def test_plain_fragment_has_no_oob(example_app) -> None:
    """A non-boosted fragment swap (just ``#page-content``) carries no OOB.

    Plain fragment swaps replace only the targeted block; the surrounding shell
    is untouched, so no out-of-band region markup is emitted.
    """
    async with TestClient(example_app) as client:
        response = await client.fragment("/")
        assert response.status == 200
        assert "hx-swap-oob" not in response.text
        # Plain fragment is the inner block only — no surrounding <main> shell.
        assert 'id="main"' not in response.text


async def test_boosted_navigation_emits_oob(example_app) -> None:
    """A boosted shell navigation re-renders the layout and appends OOB markup.

    ``hx-boost`` navigations swap the shell, so the layout chain appends its
    out-of-band region(s) as ``hx-swap-oob`` markup after the main document —
    the opposite of the suppressed full-page render.
    """
    async with TestClient(example_app) as client:
        response = await client.fragment("/", headers={"HX-Boosted": "true"})
        assert response.status == 200
        assert "hx-swap-oob" in response.text
        # The full layout chain is rendered for a boosted swap.
        assert 'id="main"' in response.text
