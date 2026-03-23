"""Tests for chirp.server.htmx_debug — debug script loading and syntax."""

import os
import shutil
import subprocess
import tempfile

import pytest

from chirp.server.htmx_debug import HIGHLIGHT_PATH, HTMX_DEBUG_BOOT_JS


def test_htmx_debug_js_loads() -> None:
    """HTMX debug script loads and contains expected content."""
    assert "__chirpHtmxDebugBooted" in HTMX_DEBUG_BOOT_JS
    assert "htmx:targetError" in HTMX_DEBUG_BOOT_JS
    assert "Co-locate the target with the mutating element" in HTMX_DEBUG_BOOT_JS
    assert "htmx:beforeSwap" in HTMX_DEBUG_BOOT_JS
    assert "chirp-debug" in HTMX_DEBUG_BOOT_JS
    assert "chirp-dbg-drawer" in HTMX_DEBUG_BOOT_JS
    assert "chirp-dbg-pill" in HTMX_DEBUG_BOOT_JS
    assert "getEffectiveConfig" in HTMX_DEBUG_BOOT_JS
    assert "htmx:oobBeforeSwap" in HTMX_DEBUG_BOOT_JS


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
    assert "parseResponseHeaders" in HTMX_DEBUG_BOOT_JS
    assert "buildCurl" in HTMX_DEBUG_BOOT_JS
    assert "ChirpHtmxDebug" in HTMX_DEBUG_BOOT_JS
    assert "firePlugin" in HTMX_DEBUG_BOOT_JS
    assert "bodyPreview" in HTMX_DEBUG_BOOT_JS
    assert "Export JSON" in HTMX_DEBUG_BOOT_JS
    assert "Pause capture" in HTMX_DEBUG_BOOT_JS
    assert "Redact curl" in HTMX_DEBUG_BOOT_JS
    assert "Copy curl" in HTMX_DEBUG_BOOT_JS


def test_htmx_debug_js_v3_sse_monitor() -> None:
    """V3: SSE/EventSource monkey-patch and monitor tab."""
    assert "EventSource" in HTMX_DEBUG_BOOT_JS
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
