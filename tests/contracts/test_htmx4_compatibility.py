"""End-to-end fail-loud provisioning contracts for htmx 4 preview (#545)."""

from pathlib import Path

import pytest

from chirp import App, AppConfig, Template
from chirp.app.htmx_manifest import HTMX4_PREVIEW_VERSION, compile_htmx_manifest
from chirp.contracts import check_hypermedia_surface
from chirp.contracts.rules_htmx_compatibility import check_htmx_compatibility
from chirp.contracts.types import Severity

pytestmark = pytest.mark.issue(545)


def _preview_bundle(*, order: tuple[str, ...] = ("core", "compat", "sse")) -> str:
    sources = {
        "core": "/assets/htmx.js",
        "compat": "/assets/htmx-2-compat.js",
        "sse": "/assets/hx-sse.js",
    }
    return "".join(
        (
            f'<script src="{sources[role]}" '
            f'data-chirp="{"htmx" if role == "core" else "htmx-extension"}" '
            + (
                'data-chirp-htmx-role="core" '
                if role == "core"
                else f'data-chirp-htmx-extension="{role}" '
            )
            + 'data-chirp-htmx-tier="4-preview" '
            + f'data-chirp-htmx-version="{HTMX4_PREVIEW_VERSION}"></script>'
        )
        for role in order
    )


def _preview_manifest():
    return compile_htmx_manifest(enabled=True, version=HTMX4_PREVIEW_VERSION)


def test_complete_marked_self_hosted_preview_bundle_passes() -> None:
    disabled = compile_htmx_manifest(enabled=False, version="2.0.10")
    assert check_htmx_compatibility({"layout.html": _preview_bundle()}, disabled) == []


def test_missing_duplicate_mismatched_and_misordered_assets_are_errors() -> None:
    sources = {
        "missing.html": _preview_bundle(order=("core",)),
        "duplicate.html": _preview_bundle(order=("core", "compat", "compat", "sse")),
        "order.html": _preview_bundle(order=("compat", "core", "sse")),
        "version.html": _preview_bundle().replace(HTMX4_PREVIEW_VERSION, "4.0.0-beta6"),
        "role.html": _preview_bundle().replace(
            'src="/assets/htmx-2-compat.js"',
            'src="/assets/hx-sse.js"',
            1,
        ),
    }
    issues = check_htmx_compatibility(sources, _preview_manifest())

    assert issues
    assert all(issue.category == "htmx_compatibility" for issue in issues)
    assert all(issue.severity is Severity.ERROR for issue in issues)
    messages = "\n".join(issue.message for issue in issues)
    assert "missing the 'compat' script" in messages
    assert "declares 2 'compat' scripts" in messages
    assert "out of order" in messages
    assert "4.0.0-beta6" in messages
    assert "source is the 'sse' asset" in messages
    assert all(issue.template in sources for issue in issues)


def test_managed_injection_rejects_unmarked_manual_core() -> None:
    sources = {
        "layout.html": '<script src="/assets/htmx.min.js"></script>',
    }
    issues = check_htmx_compatibility(sources, _preview_manifest())
    assert any("would load twice" in issue.message for issue in issues)


def test_version_specific_sse_markup_is_checked() -> None:
    stable = compile_htmx_manifest(enabled=True, version="2.0.10")
    stable_issues = check_htmx_compatibility(
        {"page.html": '<div hx-sse:connect="/events"></div>'},
        stable,
    )
    assert any("htmx 4 hx-sse:*" in issue.message for issue in stable_issues)

    preview_issues = check_htmx_compatibility(
        {"page.html": '<div sse-connect="/events" sse-swap="message"></div>'},
        _preview_manifest(),
    )
    assert any("removed sse-*" in issue.message for issue in preview_issues)


def _app(tmp_path: Path, template: str) -> App:
    (tmp_path / "page.html").write_text(template, encoding="utf-8")
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

    return app


@pytest.mark.parametrize("debug", [False, True])
def test_incomplete_manual_bundle_reaches_real_app_check(tmp_path: Path, debug: bool) -> None:
    template = """<html><body>
<script src="/htmx.js" data-chirp="htmx"
  data-chirp-htmx-tier="4-preview"
  data-chirp-htmx-version="4.0.0-beta5"></script>
</body></html>"""
    (tmp_path / "page.html").write_text(template, encoding="utf-8")
    app = App(
        AppConfig(
            debug=debug,
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
    assert issues
    assert all(issue.severity is Severity.ERROR for issue in issues)
    assert any("missing the 'compat' script" in issue.message for issue in issues)
    assert all(issue.template == "page.html" for issue in issues)


def test_managed_preview_without_manual_scripts_is_clean(tmp_path: Path) -> None:
    app = _app(tmp_path, '<html><body><button hx-get="/">Load</button></body></html>')
    categories = {issue.category for issue in check_hypermedia_surface(app).issues}
    assert "htmx_compatibility" not in categories
