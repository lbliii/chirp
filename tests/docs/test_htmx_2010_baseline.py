"""Repository-wide source contract for the verified htmx 2.0.10 baseline."""

import re
from pathlib import Path

import pytest

from chirp import AppConfig

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOTS = ("src", "tests", "examples", "site/content")
HTMX2_CORE_URL = re.compile(r"https://[^\"' ]+/htmx\.org@2\.[0-9.]+/dist/htmx(?:\.min)?\.js")
EXPECTED_URL = "https://cdn.jsdelivr.net/npm/htmx.org@2.0.10/dist/htmx.min.js"
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"


@pytest.mark.issue(543)
def test_default_is_verified_htmx_2010() -> None:
    assert AppConfig().htmx_version == "2.0.10"


@pytest.mark.issue(543)
def test_authored_sources_have_no_old_baseline_or_noncanonical_core_url() -> None:
    old_version = "2.0." + "4"
    stale: list[str] = []
    noncanonical: list[str] = []
    for root_name in SOURCE_ROOTS:
        for path in (ROOT / root_name).rglob("*"):
            if not path.is_file() or path.suffix not in {".html", ".md", ".py"}:
                continue
            text = path.read_text(encoding="utf-8")
            if old_version in text:
                stale.append(str(path.relative_to(ROOT)))
            noncanonical.extend(
                f"{path.relative_to(ROOT)}: {url}"
                for url in HTMX2_CORE_URL.findall(text)
                if url != EXPECTED_URL
            )

    assert stale == []
    assert noncanonical == []


@pytest.mark.issue(543)
def test_browser_smoke_preserves_chirp_ui_floor_after_final_sync() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    chromium = workflow.index("      - name: Install Chromium")
    floor = workflow.index("      - name: Pin Lucky Cat browser compatibility floor")
    smoke = workflow.index("      - name: Browser smoke")

    assert chromium < floor < smoke
    assert "uv run --no-sync pytest" in workflow[floor : smoke + 200]
