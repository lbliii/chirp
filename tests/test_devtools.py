"""Tests for chirp.server.devtools — Chirp DevTools (⌁⌁) script loading and syntax."""

import os
import shutil
import subprocess
import tempfile

import pytest

from chirp.server.devtools import DEVTOOLS_BOOT_JS as HTMX_DEBUG_BOOT_JS
from chirp.server.devtools import HIGHLIGHT_PATH


def test_htmx_debug_js_loads() -> None:
    """Chirp DevTools script loads and contains expected content."""
    assert "__chirpHtmxDebugBooted" in HTMX_DEBUG_BOOT_JS
    assert "htmx:targetError" in HTMX_DEBUG_BOOT_JS
    assert "Co-locate the target with the mutating element" in HTMX_DEBUG_BOOT_JS
    assert "htmx:beforeSwap" in HTMX_DEBUG_BOOT_JS
    assert "chirp-debug" in HTMX_DEBUG_BOOT_JS
    assert "chirp-dbg-drawer" in HTMX_DEBUG_BOOT_JS
    assert "chirp-dbg-pill" in HTMX_DEBUG_BOOT_JS
    assert "getEffectiveConfig" in HTMX_DEBUG_BOOT_JS
    assert "htmx:oobBeforeSwap" in HTMX_DEBUG_BOOT_JS


def test_htmx_debug_js_chirp_branding() -> None:
    """Pill shows ⌁⌁ Chirp logo, not 'HTMX'."""
    assert "\\u2301\\u2301" in HTMX_DEBUG_BOOT_JS
    assert "Chirp DevTools" in HTMX_DEBUG_BOOT_JS
    assert "chirp devtools active" in HTMX_DEBUG_BOOT_JS


def test_htmx_debug_js_parses_route_headers() -> None:
    """HTMX debug script parses X-Chirp-Route-* headers for activity log."""
    assert "X-Chirp-Route-Kind" in HTMX_DEBUG_BOOT_JS
    assert "getResponseHeader" in HTMX_DEBUG_BOOT_JS
    assert "r.route" in HTMX_DEBUG_BOOT_JS


def test_htmx_debug_js_parses_layout_headers() -> None:
    """HTMX debug script captures X-Chirp-Layout-* from Chirp debug middleware."""
    assert "X-Chirp-Layout-Chain" in HTMX_DEBUG_BOOT_JS
    assert "X-Chirp-Layout-Match" in HTMX_DEBUG_BOOT_JS
    assert "X-Chirp-Layout-Mode" in HTMX_DEBUG_BOOT_JS
    assert "r.layout" in HTMX_DEBUG_BOOT_JS


def test_htmx_debug_js_enhanced_ui_strings() -> None:
    """Tray exposes shortcuts, help strip, copy, and optional verbose logging."""
    assert "chirp-dbg-help" in HTMX_DEBUG_BOOT_JS
    assert "chirp-debug-verbose" in HTMX_DEBUG_BOOT_JS
    assert "Copy all" in HTMX_DEBUG_BOOT_JS
    assert "RTT (sent" in HTMX_DEBUG_BOOT_JS
    assert "Layout" in HTMX_DEBUG_BOOT_JS


def test_htmx_debug_js_s_tier_features() -> None:
    """S-tier: render intent header, HX response parse, curl, export, hooks, error body."""
    assert "x-chirp-render-intent" in HTMX_DEBUG_BOOT_JS
    assert "X-Chirp-Return-Trace" in HTMX_DEBUG_BOOT_JS
    assert "returnTrace" in HTMX_DEBUG_BOOT_JS
    assert "parseResponseHeaders" in HTMX_DEBUG_BOOT_JS
    assert "buildCurl" in HTMX_DEBUG_BOOT_JS
    assert "ChirpHtmxDebug" in HTMX_DEBUG_BOOT_JS
    assert "firePlugin" in HTMX_DEBUG_BOOT_JS
    assert "bodyPreview" in HTMX_DEBUG_BOOT_JS
    assert "Export JSON" in HTMX_DEBUG_BOOT_JS
    assert "Pause capture" in HTMX_DEBUG_BOOT_JS
    assert "Redact curl" in HTMX_DEBUG_BOOT_JS
    assert "Copy curl" in HTMX_DEBUG_BOOT_JS
    assert "CH.help = function" in HTMX_DEBUG_BOOT_JS
    assert "enabledBy" in HTMX_DEBUG_BOOT_JS
    assert "exportRecordsJson" in HTMX_DEBUG_BOOT_JS


def test_htmx_debug_js_v3_sse_monitor() -> None:
    """V3: SSE monitor consumes native Chirp EventStream traces."""
    assert "window.EventSource =" not in HTMX_DEBUG_BOOT_JS
    assert "ChirpTrackedEventSource" not in HTMX_DEBUG_BOOT_JS
    assert "DEBUG_TRACES_PATH" in HTMX_DEBUG_BOOT_JS
    assert "ingestNativeSseTrace" in HTMX_DEBUG_BOOT_JS
    assert "sseConnections" in HTMX_DEBUG_BOOT_JS
    assert "sseEvents" in HTMX_DEBUG_BOOT_JS
    assert "renderSseLog" in HTMX_DEBUG_BOOT_JS


def test_htmx_debug_js_v3_waterfall() -> None:
    """V3: Network waterfall inline bars."""
    assert "renderWaterfall" in HTMX_DEBUG_BOOT_JS
    assert "chirp-dbg-waterfall" in HTMX_DEBUG_BOOT_JS
    assert "chirp-dbg-wf-seg" in HTMX_DEBUG_BOOT_JS


def test_htmx_debug_js_v3_view_transitions() -> None:
    """V3: View Transition lifecycle tracking."""
    assert "startViewTransition" in HTMX_DEBUG_BOOT_JS
    assert "vtEvents" in HTMX_DEBUG_BOOT_JS
    assert "chirp-dbg-vt-row" in HTMX_DEBUG_BOOT_JS


def test_htmx_debug_js_v3_dom_diff() -> None:
    """V3: DOM diff captures before/after swap state."""
    assert "domBefore" in HTMX_DEBUG_BOOT_JS
    assert "domAfter" in HTMX_DEBUG_BOOT_JS
    assert "domDiff" in HTMX_DEBUG_BOOT_JS
    assert "diffLines" in HTMX_DEBUG_BOOT_JS
    assert "hlDiff" in HTMX_DEBUG_BOOT_JS


def test_htmx_debug_js_v3_render_plan() -> None:
    """V3: Render plan inspector decodes X-Chirp-Render-Plan header."""
    assert "X-Chirp-Render-Plan" in HTMX_DEBUG_BOOT_JS
    assert "decodeRenderPlan" in HTMX_DEBUG_BOOT_JS
    assert "formatRenderPlan" in HTMX_DEBUG_BOOT_JS
    assert "renderPlan" in HTMX_DEBUG_BOOT_JS


def test_htmx_debug_js_swap_doctor() -> None:
    """DevTools explains swap behavior instead of only logging htmx events."""
    assert "Swap Doctor" in HTMX_DEBUG_BOOT_JS
    assert "buildSwapDoctor" in HTMX_DEBUG_BOOT_JS
    assert "renderSwapDoctorHTML" in HTMX_DEBUG_BOOT_JS
    assert "responseContainsSelector" in HTMX_DEBUG_BOOT_JS
    assert "selectMatched" in HTMX_DEBUG_BOOT_JS
    assert "full HTML document arrived for an htmx request" in HTMX_DEBUG_BOOT_JS


def test_htmx_debug_js_request_correlation() -> None:
    """Overlapping htmx requests are correlated by XHR when available."""
    assert "recordByXhr" in HTMX_DEBUG_BOOT_JS
    assert "WeakMap" in HTMX_DEBUG_BOOT_JS
    assert "getRecordForDetail" in HTMX_DEBUG_BOOT_JS
    assert "rememberRecordForDetail" in HTMX_DEBUG_BOOT_JS


def test_htmx_debug_js_inspector_shows_inheritance_sources() -> None:
    """Inspector records whether hx-* values are direct, inherited, blocked, or default."""
    assert "getEffectiveConfigDetails" in HTMX_DEBUG_BOOT_JS
    assert "formatConfigDetails" in HTMX_DEBUG_BOOT_JS
    assert "hx-disinherit" in HTMX_DEBUG_BOOT_JS
    assert '"direct" : "inherited"' in HTMX_DEBUG_BOOT_JS
    assert 'source: "blocked"' in HTMX_DEBUG_BOOT_JS


def test_htmx_debug_js_v3_syntax_highlight() -> None:
    """V3: Client-side syntax highlighting for JSON, headers, diffs."""
    assert "hlJSON" in HTMX_DEBUG_BOOT_JS
    assert "hlHeaders" in HTMX_DEBUG_BOOT_JS
    assert "hlDiff" in HTMX_DEBUG_BOOT_JS
    assert HIGHLIGHT_PATH in HTMX_DEBUG_BOOT_JS


def test_htmx_debug_js_valid_syntax() -> None:
    """HTMX debug script is valid JavaScript (catches escaping/quote errors).

    Uses node --check when available. Skips if node is not installed.
    """
    node = shutil.which("node")
    if not node:
        pytest.skip("node not found — install Node.js to validate JS syntax")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(HTMX_DEBUG_BOOT_JS)
        path = f.name

    try:
        result = subprocess.run(
            [node, "--check", path],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0, f"JS syntax error: {result.stderr or result.stdout}"
    finally:
        os.unlink(path)
