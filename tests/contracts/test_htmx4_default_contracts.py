"""Fail-loud contracts for material htmx 4 default changes (#548)."""

from pathlib import Path

import pytest

from chirp import App, AppConfig, Template
from chirp.app.htmx_manifest import HTMX4_PREVIEW_VERSION, compile_htmx_manifest
from chirp.contracts import check_hypermedia_surface
from chirp.contracts.rules_htmx_compatibility import check_htmx_compatibility
from chirp.contracts.types import ContractIssue, Severity

pytestmark = pytest.mark.issue(548)


def _manifest(version: str = HTMX4_PREVIEW_VERSION):
    return compile_htmx_manifest(enabled=True, version=version)


def _find(issues: list[ContractIssue], construct: str) -> ContractIssue:
    return next(issue for issue in issues if repr(construct) in issue.message)


def test_removed_trigger_queue_is_an_error_with_hx_sync_remediation() -> None:
    issues = check_htmx_compatibility(
        {"page.html": '<button hx-post="/save" hx-trigger="click queue:last">Save</button>'},
        _manifest(),
    )
    issue = _find(issues, 'hx-trigger="click queue:last"')
    assert issue.severity is Severity.ERROR
    assert issue.details == "Detected at line 1."
    assert "hx-sync" in issue.message


def test_hx_sync_replacement_is_clean() -> None:
    source = '<button hx-post="/save" hx-trigger="click" hx-sync="this:queue last">Save</button>'
    assert check_htmx_compatibility({"page.html": source}, _manifest()) == []


def test_delete_form_data_requires_explicit_include() -> None:
    source = """<form>
  <input name="item_id" value="42">
  <button hx-delete="/items/42">Delete</button>
</form>"""
    issues = check_htmx_compatibility({"page.html": source}, _manifest())
    issue = _find(issues, "hx-delete inside a form without hx-include")
    assert issue.severity is Severity.WARNING
    assert "named values are not sent" in issue.message

    included = source.replace(
        'hx-delete="/items/42"', 'hx-delete="/items/42" hx-include="closest form"'
    )
    assert check_htmx_compatibility({"page.html": included}, _manifest()) == []


def test_delete_that_drops_csrf_field_is_an_error() -> None:
    source = """<form>
  <input type="hidden" name="_csrf_token" value="token">
  <button hx-delete="/items/42">Delete</button>
</form>"""
    issues = check_htmx_compatibility({"page.html": source}, _manifest())
    issue = _find(issues, "hx-delete inside a form without hx-include")
    assert issue.severity is Severity.ERROR
    assert "_csrf_token" in issue.message


def test_pushed_history_requires_stable_refetch_boundary() -> None:
    source = '<a href="/next" hx-boost="true" hx-push-url="true">Next</a>'
    issues = check_htmx_compatibility({"page.html": source}, _manifest())
    issue = _find(issues, "hx-push-url")
    assert issue.severity is Severity.WARNING
    assert "refetches history" in issue.message

    shell = (
        '<main hx-history-elt><a href="/next" hx-boost="true" hx-push-url="true">Next</a></main>'
    )
    assert check_htmx_compatibility({"page.html": shell}, _manifest()) == []


@pytest.mark.parametrize("target", ["body", "#shell", "#missing"])
def test_explicit_5xx_swap_rejects_broad_or_unresolved_targets(target: str) -> None:
    source = f'<main id="shell"></main><button hx-get="/fail" hx-target="{target}" hx-status:5xx="swap:innerHTML">Fail</button>'
    issues = check_htmx_compatibility({"page.html": source}, _manifest())
    issue = _find(issues, "hx-status:5xx")
    assert issue.severity is Severity.ERROR
    assert target in issue.message


def test_explicit_5xx_swap_allows_local_target_or_swap_none() -> None:
    local = '<div id="error"></div><button hx-get="/fail" hx-target="#error" hx-status:5xx="swap:innerHTML">Fail</button>'
    no_swap = '<button hx-get="/fail" hx-target="body" hx-status:5xx="swap:none">Fail</button>'
    assert check_htmx_compatibility({"local.html": local}, _manifest()) == []
    assert check_htmx_compatibility({"none.html": no_swap}, _manifest()) == []


def test_default_contract_rules_do_not_apply_to_htmx2() -> None:
    source = """<form><input name="item"><button hx-delete="/item"
      hx-trigger="click queue:last" hx-push-url="true">Delete</button></form>"""
    assert check_htmx_compatibility({"page.html": source}, _manifest("2.0.10")) == []


def test_queue_failure_reaches_real_app_check(tmp_path: Path) -> None:
    (tmp_path / "page.html").write_text(
        '<button hx-post="/save" hx-trigger="click queue:last">Save</button>',
        encoding="utf-8",
    )
    app = App(
        AppConfig(
            htmx=True,
            htmx_version=HTMX4_PREVIEW_VERSION,
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
    issue = _find(issues, 'hx-trigger="click queue:last"')
    assert issue.severity is Severity.ERROR
    assert issue.template == "page.html"
