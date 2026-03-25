"""Tests for htmx 4.0 <htmx-partial> alignment."""

from chirp.contracts.template_scan import extract_htmx_partial_sources
from chirp.http.headers import Headers
from chirp.http.request import HtmxDetails


class TestHtmxPartialHeader:
    """HtmxDetails.partial parses HX-Partial header."""

    def test_partial_present(self):
        headers = Headers(((b"hx-request", b"true"), (b"hx-partial", b"sidebar")))
        details = HtmxDetails(headers, None)
        assert details.partial == "sidebar"

    def test_partial_absent(self):
        headers = Headers(((b"hx-request", b"true"),))
        details = HtmxDetails(headers, None)
        assert details.partial is None


class TestExtractHtmxPartialSources:
    """Extract src= from <htmx-partial> elements."""

    def test_static_src(self):
        source = '<htmx-partial src="/sidebar"></htmx-partial>'
        assert extract_htmx_partial_sources(source) == ["/sidebar"]

    def test_dynamic_src_skipped(self):
        source = '<htmx-partial src="{{ url }}"></htmx-partial>'
        assert extract_htmx_partial_sources(source) == []

    def test_multiple_partials(self):
        source = (
            '<htmx-partial src="/header"></htmx-partial>'
            '<htmx-partial src="/footer"></htmx-partial>'
        )
        assert extract_htmx_partial_sources(source) == ["/header", "/footer"]

    def test_no_partials(self):
        assert extract_htmx_partial_sources("<div>hello</div>") == []
