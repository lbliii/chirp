"""Tests for chirp.server.htmx_debug — debug script loading and syntax."""

import os
import shutil
import subprocess
import tempfile

import pytest

from chirp.server.htmx_debug import HTMX_DEBUG_BOOT_JS


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
