"""Published HTTP QUERY interoperability claims stay aligned with #532."""

from pathlib import Path

_ROOT = Path(__file__).parents[2]


def test_query_interoperability_report_names_executable_evidence() -> None:
    report = (_ROOT / "docs/http-query-interoperability.md").read_text()
    workflow = (_ROOT / ".github/workflows/ci.yml").read_text()
    wire_tests = (_ROOT / "tests/interop/test_query_wire.py").read_text()

    for claim in (
        "Pounce HTTP/1.1",
        "Pounce HTTP/2",
        "Pounce HTTP/3",
        "Uvicorn 0.32.0",
        "Nginx reverse proxy",
        "Browser CORS",
        "0-RTT",
    ):
        assert claim in report
    assert "query-interop:" in workflow
    assert "bengal-pounce[h2,h3]==0.8.2" in workflow
    assert "tests/contracts/test_query_cors_browser.py" in workflow
    assert "test_pounce_http1_raw_wire_preserves_query_method_and_body" in wire_tests
    assert "test_nginx_reverse_proxy_preserves_query_method_and_body" in wire_tests


def test_query_interoperability_docs_preserve_experimental_caveats() -> None:
    report = (_ROOT / "docs/http-query-interoperability.md").read_text()
    site = (_ROOT / "site/content/docs/quality/deployment/query-interoperability.md").read_text()
    rfc = (_ROOT / "docs/rfcs/009-http-query.md").read_text()

    assert "does not promote QUERY to a stable" in report
    assert "No CDN is certified" in report
    assert "never rewrite query to post" in " ".join(report.lower().split())
    assert "remains experimental and explicit-route only" in site
    assert "#532 interoperability proof implemented" in rfc
