"""Tests for the page_handlers contract check."""

from pathlib import Path

from chirp import App, AppConfig
from chirp.contracts import check_hypermedia_surface
from chirp.contracts.types import Severity


def test_page_with_no_handlers_produces_error(tmp_path: Path) -> None:
    """A page.py with no handler-shaped functions registers no routes — must ERROR."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "page.py").write_text("x = 1\n")
    (pages_dir / "page.html").write_text("<html></html>")

    app = App(AppConfig(template_dir=str(pages_dir), debug=True, skip_contract_checks=True))
    app.mount_pages(str(pages_dir))

    result = check_hypermedia_surface(app)
    issues = [i for i in result.issues if i.category == "page_handlers"]
    assert len(issues) == 1
    assert issues[0].severity == Severity.ERROR
    assert issues[0].route == "/"
    assert "no recognised HTTP method handler" in (issues[0].message or "")


def test_page_with_handle_typo_produces_warning_and_missing_error(
    tmp_path: Path,
) -> None:
    """``def handle()`` is handler-shaped — emits typo WARNING + missing ERROR."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "page.py").write_text("def handle(): return {}")
    (pages_dir / "page.html").write_text("<html></html>")

    app = App(AppConfig(template_dir=str(pages_dir), debug=True, skip_contract_checks=True))
    app.mount_pages(str(pages_dir))

    result = check_hypermedia_surface(app)
    by_sev: dict[Severity, list] = {}
    for issue in result.issues:
        if issue.category == "page_handlers":
            by_sev.setdefault(issue.severity, []).append(issue)
    assert len(by_sev.get(Severity.WARNING, [])) == 1
    assert "handle" in (by_sev[Severity.WARNING][0].message or "")
    assert len(by_sev.get(Severity.ERROR, [])) == 1


def test_page_with_get_is_clean(tmp_path: Path) -> None:
    """A page.py with ``def get()`` registers a route and emits no issues."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "page.py").write_text("def get(): return {}")
    (pages_dir / "page.html").write_text("<html></html>")

    app = App(AppConfig(template_dir=str(pages_dir), debug=True, skip_contract_checks=True))
    app.mount_pages(str(pages_dir))

    result = check_hypermedia_surface(app)
    issues = [i for i in result.issues if i.category == "page_handlers"]
    assert issues == []


def test_page_with_bare_handler_is_clean(tmp_path: Path) -> None:
    """``def handler()`` is an accepted fallback — no issues."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "page.py").write_text("def handler(): return {}")
    (pages_dir / "page.html").write_text("<html></html>")

    app = App(AppConfig(template_dir=str(pages_dir), debug=True, skip_contract_checks=True))
    app.mount_pages(str(pages_dir))

    result = check_hypermedia_surface(app)
    issues = [i for i in result.issues if i.category == "page_handlers"]
    assert issues == []


def test_severity_override_demotes_missing_to_warning(tmp_path: Path) -> None:
    """``override_contract_severity`` can soften the missing-handler ERROR."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "page.py").write_text("def handle(): return {}")
    (pages_dir / "page.html").write_text("<html></html>")

    app = App(AppConfig(template_dir=str(pages_dir), debug=True, skip_contract_checks=True))
    app.override_contract_severity("page_handlers", Severity.WARNING)
    app.mount_pages(str(pages_dir))

    result = check_hypermedia_surface(app)
    issues = [i for i in result.issues if i.category == "page_handlers"]
    assert issues
    assert all(i.severity == Severity.WARNING for i in issues)
