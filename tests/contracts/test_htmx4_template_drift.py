"""Tier-aware htmx 2/4 template drift contracts (#547)."""

from pathlib import Path

import pytest

from chirp import App, AppConfig, Template
from chirp.app.htmx_manifest import HTMX4_PREVIEW_VERSION, compile_htmx_manifest
from chirp.contracts import check_hypermedia_surface
from chirp.contracts.rules_htmx_compatibility import check_htmx_compatibility
from chirp.contracts.types import ContractIssue, Severity

pytestmark = pytest.mark.issue(547)


def _stable():
    return compile_htmx_manifest(enabled=True, version="2.0.10")


def _preview():
    return compile_htmx_manifest(enabled=True, version=HTMX4_PREVIEW_VERSION)


def _find(issues: list[ContractIssue], construct: str) -> ContractIssue:
    return next(issue for issue in issues if repr(construct) in issue.message)


def test_preview_reports_compatibility_debt_as_line_aware_warnings() -> None:
    source = """<main hx-confirm="Sure?" hx-ext="sse">
  <button hx-post="/save" hx-disabled-elt="this">Save</button>
  <script>
    document.addEventListener("htmx:afterSwap", update);
    htmx.config.defaultSwapStyle = "outerHTML";
  </script>
</main>"""
    issues = check_htmx_compatibility({"page.html": source}, _preview())

    for construct, line in {
        "hx-ext": 1,
        "implicit hx-confirm inheritance": 2,
        "hx-disabled-elt": 2,
        "htmx:afterSwap": 4,
        "htmx.config.defaultSwapStyle": 5,
    }.items():
        issue = _find(issues, construct)
        assert issue.severity is Severity.WARNING
        assert issue.template == "page.html"
        assert issue.details == f"Detected at line {line}."
        assert "Configured tier '4-preview'" in issue.message
        assert "Remediation:" in issue.message


def test_preview_errors_name_constructs_that_compatibility_cannot_make_safe() -> None:
    source = """<div hx-disable>
  <div sse-connect="/events" sse-swap="message"></div>
  <script>document.addEventListener("htmx:xhr:progress", progress)</script>
</div>"""
    issues = check_htmx_compatibility({"page.html": source}, _preview())

    for construct in ("hx-disable", "sse-connect", "sse-swap", "htmx:xhr:progress"):
        issue = _find(issues, construct)
        assert issue.severity is Severity.ERROR
        assert "Remediation:" in issue.message


def test_stable_tier_rejects_htmx4_attributes_and_lifecycle_events() -> None:
    source = """<form hx-action="/save" hx-method="post"
  hx-config="credentials:include" hx-status:422="swap:none">
  <button hx-confirm:inherited="Sure?">Save</button>
</form>
<script>document.addEventListener("htmx:after:request", done)</script>"""
    issues = check_htmx_compatibility({"page.html": source}, _stable())

    for construct in (
        "hx-action",
        "hx-method",
        "hx-config",
        "hx-status:422",
        "hx-confirm:inherited",
        "htmx:after:request",
    ):
        issue = _find(issues, construct)
        assert issue.severity is Severity.ERROR
        assert "Configured tier '2-managed'" in issue.message
        assert "inert" in issue.message or "does not emit" in issue.message


def test_version_native_templates_are_clean() -> None:
    stable = """<div hx-confirm="Sure?" hx-ext="sse">
  <button hx-post="/save" hx-disable>Save</button>
</div>
<script>document.addEventListener("htmx:afterSwap", done)</script>"""
    preview = """<form hx-action="/save" hx-method="post" hx-config="credentials:include"
  hx-confirm:inherited="Sure?" hx-status:422="swap:none">
  <button>Save</button>
</form>
<script>document.addEventListener("htmx:after:request", done)</script>"""

    assert check_htmx_compatibility({"stable.html": stable}, _stable()) == []
    assert check_htmx_compatibility({"preview.html": preview}, _preview()) == []


def test_unmarked_conditional_multi_version_fixture_has_no_inferred_tier() -> None:
    disabled = compile_htmx_manifest(enabled=False, version="2.0.10")
    source = """{% if preview %}
<script src="https://cdn.example/htmx.org@4.0.0-beta5/dist/htmx.min.js"></script>
{% else %}
<script src="https://cdn.jsdelivr.net/npm/htmx.org@2.0.10/dist/htmx.min.js"></script>
{% endif %}
<button hx-validate hx-post="/save">Save</button>"""
    assert check_htmx_compatibility({"matrix.html": source}, disabled) == []


def test_code_samples_comments_and_dynamic_attribute_bundles_are_ignored() -> None:
    source = """<pre><code><div hx-disable sse-connect="/events"></div></code></pre>
<div {{ attrs | html_attrs }}>Dynamic attributes</div>
<script>
  // document.addEventListener("htmx:afterSwap", oldHandler)
  /* htmx.config.defaultSwapStyle = "outerHTML"; */
  document.addEventListener("htmx:after:request", currentHandler)
</script>"""
    assert check_htmx_compatibility({"docs.html": source}, _preview()) == []


def test_explicit_descendant_override_reports_only_the_nearest_dependency() -> None:
    source = """<main hx-target="#outer">
  <section hx-target="#local">
    <button hx-post="/save">Save</button>
    </section>
</main>"""
    issues = check_htmx_compatibility({"page.html": source}, _preview())
    inheritance = [issue for issue in issues if "implicit hx-target inheritance" in issue.message]
    assert len(inheritance) == 1
    assert "ancestor at line 2" in inheritance[0].message


@pytest.mark.parametrize(
    ("version", "template", "severity", "construct"),
    [
        (
            HTMX4_PREVIEW_VERSION,
            '<main hx-confirm="Sure?"><button hx-post="/save">Save</button></main>',
            Severity.WARNING,
            "implicit hx-confirm inheritance",
        ),
        (
            "2.0.10",
            '<button hx-action="/save" hx-method="post">Save</button>',
            Severity.ERROR,
            "hx-action",
        ),
    ],
)
def test_template_drift_reaches_real_app_check(
    tmp_path: Path,
    version: str,
    template: str,
    severity: Severity,
    construct: str,
) -> None:
    (tmp_path / "page.html").write_text(template, encoding="utf-8")
    app = App(
        AppConfig(
            htmx=True,
            htmx_version=version,
            skip_contract_checks=True,
            template_dir=tmp_path,
        )
    )

    @app.route("/")
    def index():
        return Template("page.html")

    issues = [
        issue
        for issue in check_hypermedia_surface(app).issues
        if issue.category == "htmx_compatibility"
    ]
    issue = _find(issues, construct)
    assert issue.severity is severity
    assert issue.template == "page.html"
    assert issue.details == "Detected at line 1."
