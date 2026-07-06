"""Freeze-time provisioning proof for the explicit htmx 4 preview (#545)."""

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError

import pytest

from chirp import App, AppConfig
from chirp.app.htmx_manifest import (
    HTMX4_PREVIEW_VERSION,
    HTMX_ROLLBACK_VERSION,
    compile_htmx_manifest,
)
from chirp.errors import ConfigurationError
from chirp.server.htmx import htmx_manifest_snippet
from chirp.testing import TestClient

pytestmark = pytest.mark.issue(545)


def test_manifest_preserves_disabled_and_historical_non4_behavior() -> None:
    disabled = compile_htmx_manifest(enabled=False, version=HTMX4_PREVIEW_VERSION)
    assert disabled.tier == "disabled"
    assert disabled.assets == ()

    managed = compile_htmx_manifest(enabled=True, version="2.1.0")
    assert managed.tier == "2-managed"
    assert [asset.role for asset in managed.assets] == ["core"]
    assert managed.assets[0].url.endswith("htmx.org@2.1.0/dist/htmx.min.js")
    assert managed.rollback_version == HTMX_ROLLBACK_VERSION


def test_verified_rollback_and_scaffold_default_remain_htmx2() -> None:
    from pathlib import Path

    assert AppConfig().htmx_version == HTMX_ROLLBACK_VERSION
    rollback = compile_htmx_manifest(enabled=True, version=HTMX_ROLLBACK_VERSION)
    assert rollback.tier == "2-managed"
    assert [asset.role for asset in rollback.assets] == ["core"]

    scaffold = (Path(__file__).resolve().parents[1] / "src/chirp/cli/templates/v2.py").read_text(
        encoding="utf-8"
    )
    assert "htmx.org@2.0.10/dist/htmx.min.js" in scaffold
    assert "4.0.0-beta5" not in scaffold


def test_preview_manifest_is_exact_ordered_and_immutable() -> None:
    manifest = compile_htmx_manifest(enabled=True, version=HTMX4_PREVIEW_VERSION)

    assert manifest.tier == "4-preview"
    assert [asset.role for asset in manifest.assets] == ["core", "compat", "sse"]
    assert [asset.url.rsplit("/", 1)[-1] for asset in manifest.assets] == [
        "htmx.min.js",
        "htmx-2-compat.min.js",
        "hx-sse.min.js",
    ]
    assert all(f"htmx.org@{HTMX4_PREVIEW_VERSION}/dist/" in asset.url for asset in manifest.assets)
    assert all(asset.sha256 for asset in manifest.assets)
    with pytest.raises(FrozenInstanceError):
        # Deliberately violate the frozen contract to prove runtime enforcement.
        manifest.version = "4.0.0"  # type: ignore[misc]


@pytest.mark.parametrize("version", ["4", "4.0.0", "4.0.0-beta6", "v4.0.0-beta5"])
def test_unknown_or_malformed_htmx4_pin_fails_before_serving(version: str) -> None:
    app = App(AppConfig(htmx=True, htmx_version=version))

    @app.route("/")
    def index():
        return "<html><body>never served</body></html>"

    with pytest.raises(ConfigurationError, match="exact provisional pin"):
        app.freeze()


def test_preview_snippet_carries_order_metadata_and_shared_nonce() -> None:
    manifest = compile_htmx_manifest(enabled=True, version=HTMX4_PREVIEW_VERSION)
    snippet = htmx_manifest_snippet(manifest, nonce="PREVIEW-NONCE")

    assert snippet.count("<script") == 3
    assert snippet.count('nonce="PREVIEW-NONCE"') == 3
    assert snippet.count('data-chirp-htmx-tier="4-preview"') == 3
    assert snippet.count(f'data-chirp-htmx-version="{HTMX4_PREVIEW_VERSION}"') == 3
    assert snippet.index("htmx.min.js") < snippet.index("htmx-2-compat.min.js")
    assert snippet.index("htmx-2-compat.min.js") < snippet.index("hx-sse.min.js")


async def test_freeze_publishes_manifest_used_by_buffered_injection() -> None:
    app = App(AppConfig(htmx=True, htmx_version=HTMX4_PREVIEW_VERSION))

    @app.route("/")
    def index():
        return "<html><body>preview</body></html>"

    async with TestClient(app) as client:
        response = await client.get("/")

    manifest = app._runtime_state.htmx_manifest
    assert manifest is not None
    assert manifest.tier == "4-preview"
    assert response.text.count(f'data-chirp-htmx-version="{HTMX4_PREVIEW_VERSION}"') == 3
    assert [response.text.index(asset.url) for asset in manifest.assets] == sorted(
        response.text.index(asset.url) for asset in manifest.assets
    )


async def test_preview_whole_bundle_dedups_on_manual_core_marker() -> None:
    app = App(AppConfig(htmx=True, htmx_version=HTMX4_PREVIEW_VERSION))

    @app.route("/")
    def index():
        return '<html><body><script data-chirp="htmx" src="/self/core.js"></script></body></html>'

    async with TestClient(app) as client:
        response = await client.get("/")

    assert response.text.count('data-chirp="htmx"') == 1
    assert "cdn.jsdelivr.net" not in response.text


async def test_preview_bundle_uses_one_live_nonce_under_csp() -> None:
    app = App(
        AppConfig(
            csp_nonce_enabled=True,
            htmx=True,
            htmx_version=HTMX4_PREVIEW_VERSION,
        )
    )

    @app.route("/")
    def index():
        return "<html><body>preview</body></html>"

    async with TestClient(app) as client:
        response = await client.get("/")

    csp = response.header("content-security-policy") or ""
    match = re.search(r"'nonce-([^']+)'", csp)
    assert match is not None
    nonce = match.group(1)
    preview_tags = re.findall(
        rf'<script[^>]+nonce="{re.escape(nonce)}"[^>]+data-chirp-htmx-tier="4-preview"[^>]*>',
        response.text,
    )
    assert len(preview_tags) == 3


async def test_preview_bundle_rewrites_streaming_html_in_order(tmp_path) -> None:
    from chirp import Stream

    (tmp_path / "stream.html").write_text(
        "<!doctype html><html><body>stream</body></html>",
        encoding="utf-8",
    )
    app = App(
        AppConfig(
            htmx=True,
            htmx_version=HTMX4_PREVIEW_VERSION,
            template_dir=tmp_path,
        )
    )

    @app.route("/")
    def index():
        return Stream("stream.html")

    async with TestClient(app) as client:
        response = await client.get("/")

    assert response.text.count('data-chirp-htmx-tier="4-preview"') == 3
    assert response.text.index("htmx.min.js") < response.text.index("htmx-2-compat.min.js")
    assert response.text.index("htmx-2-compat.min.js") < response.text.index("hx-sse.min.js")
    assert response.text.index("hx-sse.min.js") < response.text.index("</body>")


def test_freeze_publishes_one_manifest_under_concurrent_callers() -> None:
    app = App(AppConfig(htmx=True, htmx_version=HTMX4_PREVIEW_VERSION))

    @app.route("/")
    def index():
        return "ok"

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _index: app.freeze(), range(32)))

    manifest = app._runtime_state.htmx_manifest
    assert manifest is not None
    assert manifest.tier == "4-preview"
    assert app._runtime_state.frozen is True
