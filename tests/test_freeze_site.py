"""Smoke test: freeze the real site/content/docs/ directory.

Validates that the full Chirp documentation site freezes without
errors and produces the expected number of pages.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chirp import App, AppConfig
from chirp.docs import DocsPlugin
from chirp.freeze import freeze

_SITE_CONTENT = Path(__file__).resolve().parent.parent / "site" / "content" / "docs"


@pytest.fixture
def site_app(tmp_path: Path) -> App:
    """Chirp app mounted with the real site/content/docs/ directory."""
    if not _SITE_CONTENT.is_dir():
        pytest.skip("site/content/docs/ not found")

    tpl_dir = tmp_path / "templates"
    tpl_dir.mkdir()

    app = App(AppConfig(template_dir=str(tpl_dir)))
    app.mount("/docs", DocsPlugin(content_dir=_SITE_CONTENT, title="Chirp Docs"))
    return app


class TestFreezeSite:
    async def test_freeze_all_docs(self, site_app: App, tmp_path: Path) -> None:
        output = tmp_path / "dist"
        result = await freeze(site_app, output)

        # site/content/docs/ has ~69 markdown files
        assert result.pages_written >= 60, f"Only wrote {result.pages_written} pages"
        assert result.errors == [], f"Errors: {result.errors}"
        assert result.elapsed > 0

    async def test_freeze_index_exists(self, site_app: App, tmp_path: Path) -> None:
        output = tmp_path / "dist"
        await freeze(site_app, output)

        assert (output / "docs" / "index.html").exists()

    async def test_freeze_nested_page_exists(self, site_app: App, tmp_path: Path) -> None:
        output = tmp_path / "dist"
        await freeze(site_app, output)

        # Check a known nested page exists
        get_started = output / "docs" / "get-started"
        assert get_started.exists(), f"{get_started} missing"
        # At least one page under get-started/
        html_files = list(get_started.rglob("index.html"))
        assert len(html_files) >= 1

    async def test_freeze_timing(self, site_app: App, tmp_path: Path) -> None:
        """Freeze should complete in well under 10 seconds for ~70 pages."""
        output = tmp_path / "dist"
        result = await freeze(site_app, output)

        assert result.elapsed < 10.0, f"Freeze took {result.elapsed:.2f}s — too slow"
