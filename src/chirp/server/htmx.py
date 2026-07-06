"""htmx script injection from Chirp's frozen provisioning manifest.

Mirrors the Alpine injection path (``src/chirp/server/alpine.py``). When
``AppConfig(htmx=True)`` Chirp injects the htmx core ``<script>`` before
``</body>`` via :class:`~chirp.middleware.inject.StreamingHTMLInject`, dedup-aware
on ``data-chirp="htmx"`` so a document that already ships htmx (chirp-ui
``shell.html``/``boost.html``, the v2 scaffold) is left untouched.

CDN footgun (mirrors Alpine): the script ``src`` **must** use the explicit
jsDelivr ``/dist/htmx.min.js`` path. Managed injection, first-party layouts,
scaffolds, examples, and docs use that same minified browser bundle. Dedup still
matters when an application template ships its own marked tag.

The htmx core is an external ``src=`` script, but it still accepts the live
per-request CSP nonce: under a strict nonce-only ``script-src 'nonce-...'`` an
external ``<script src>`` without the nonce is blocked, so the snippet factory
threads the nonce onto the tag the same way the Alpine bootstrap does.
"""

import html

from chirp.app.htmx_manifest import HtmxProvisioningManifest, compile_htmx_manifest


def htmx_manifest_snippet(manifest: HtmxProvisioningManifest, *, nonce: str = "") -> str:
    """Render an ordered managed bundle from a freeze-time manifest."""
    nonce_attr = f' nonce="{html.escape(nonce, quote=True)}"' if nonce else ""
    tags: list[str] = []
    for asset in manifest.assets:
        marker = "htmx" if asset.role == "core" else "htmx-extension"
        role_attr = (
            ' data-chirp-htmx-role="core"'
            if asset.role == "core"
            else f' data-chirp-htmx-extension="{asset.role}"'
        )
        tags.append(
            f'<script defer src="{html.escape(asset.url, quote=True)}"{nonce_attr}'
            f' data-chirp="{marker}"{role_attr}'
            f' data-chirp-htmx-tier="{manifest.tier}"'
            f' data-chirp-htmx-version="{html.escape(manifest.version, quote=True)}"></script>'
        )
    return "\n".join(tags)


def htmx_snippet(version: str, *, nonce: str = "") -> str:
    """Build the managed htmx injection bundle for an exact version.

    The script URL uses the explicit ``/dist/htmx.min.js`` path — the framework's
    CDN convention (the same explicit-``/dist`` rule ``rules_alpine_cdn`` enforces
    for Alpine). Unlike Alpine — whose bare jsDelivr path resolves to a CommonJS
    module that throws in the browser — htmx's package ``main`` is browser-safe,
    so for htmx this is a consistency/minification choice rather than a fix for a
    hard failure; pinning ``/dist/htmx.min.js`` keeps every framework CDN URL on
    the explicit minified browser bundle.

    Args:
        version: htmx version (e.g. "2.0.10").
        nonce: When non-empty, the ``<script>`` carries a ``nonce="..."``
            attribute so it survives a nonce-based CSP that no longer ships
            ``'unsafe-inline'`` / loads only nonced scripts.

    Returns:
        The ordered managed bundle. Htmx 2 contains only core; the allowlisted
        htmx 4 preview also contains compatibility and SSE extensions.
    """
    manifest = compile_htmx_manifest(enabled=True, version=version)
    return htmx_manifest_snippet(manifest, nonce=nonce)
