"""Tests for the Chirp-managed htmx example — Mode A provisioning.

Proves the bright line of `AppConfig(htmx=True)`: the page declares `hx-*`
attributes and no htmx `<script>`, and Chirp injects the runtime. The contract
check passes (covered uniformly by tests/test_examples_contract_clean.py); these
tests assert the injection and swap behavior.
"""

from pathlib import Path

from chirp.contracts import check_hypermedia_surface
from chirp.testing import TestClient

_TEMPLATE = Path(__file__).parent / "templates" / "counter.html"


class TestInjection:
    """The page ships no htmx <script>; Chirp injects it via htmx=True."""

    async def test_template_declares_no_htmx_script(self, example_app) -> None:
        # The author's template never declares its own htmx runtime.
        assert "<script" not in _TEMPLATE.read_text()

    async def test_full_page_gets_chirp_injected_htmx(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            # Chirp injected the unpkg htmx runtime with the dedup marker.
            assert 'src="https://unpkg.com/htmx.org@2.0.4"' in response.text
            assert 'data-chirp="htmx"' in response.text
            # The page uses hx-* attributes (Mode A provisioning).
            assert 'hx-post="/increment"' in response.text


class TestSwap:
    """The increment endpoint returns just the counter fragment."""

    async def test_increment_swaps_counter(self, example_app) -> None:
        async with TestClient(example_app) as client:
            first = await client.post("/increment")
            assert first.status == 200
            assert '<div id="counter">' in first.text
            # Fragment response, not a full page.
            assert "<html>" not in first.text

            second = await client.post("/increment")
            # State advanced across requests.
            assert ">2<" in second.text.replace(" ", "").replace("\n", "")


class TestContract:
    """Mode A provisioning keeps the htmx_provisioning contract clean."""

    async def test_no_htmx_provisioning_error(self, example_app) -> None:
        result = check_hypermedia_surface(example_app)
        provisioning = [i for i in result.issues if i.category == "htmx_provisioning"]
        assert provisioning == []
