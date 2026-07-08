"""Source-backed status checks for live-preserving reload RFC #341."""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_RFC = _ROOT / "docs" / "rfcs" / "019-live-preserving-template-reload.md"


@pytest.mark.issue(341)
def test_live_reload_rfc_is_explicitly_non_shipping() -> None:
    text = _RFC.read_text(encoding="utf-8")

    assert "**Status:** Proposed" in text
    assert "does not change `AppConfig`" in text
    assert "a new public `AppConfig` field in this RFC" in text
    assert "No changelog: proposed RFC only" in text


@pytest.mark.issue(341)
def test_live_reload_rfc_cites_current_reload_and_render_evidence() -> None:
    text = _RFC.read_text(encoding="utf-8")

    for path in (
        "src/chirp/server/dev_browser_reload.py",
        "src/chirp/server/debug_runtime.py",
        "src/chirp/templating/integration.py",
        "src/chirp/templating/fragment_target_registry.py",
        "src/chirp/server/fragment_dispatch.py",
        "src/chirp/templating/oob_registry.py",
        "src/chirp/templating/suspense.py",
        "tests/test_dev_browser_reload.py",
    ):
        assert path in text
    assert "block_hash" in text
    assert "clear_template_cache([name])" in text


@pytest.mark.issue(341)
def test_live_reload_rfc_preserves_fail_loud_and_stream_gates() -> None:
    text = _RFC.read_text(encoding="utf-8")

    assert "an empty swap: the existing DOM stays visible" in text
    assert "connection owner is never a patch target" in text
    assert "does not patch an active Suspense target" in text
    assert "separate implementation" in text
    assert "Five Lucky Cat edits preserve one continuously updating signal connection" in text
