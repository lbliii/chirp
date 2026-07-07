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
import json
from dataclasses import dataclass
from typing import Any

from chirp.app.htmx_manifest import HtmxProvisioningManifest, compile_htmx_manifest

_REMOVED_TIMING_HEADERS = {
    "hx-trigger-after-swap": (
        "Response.with_hx_trigger_after_swap()",
        "htmx:before:settle",
    ),
    "hx-trigger-after-settle": (
        "Response.with_hx_trigger_after_settle()",
        "htmx:after:settle",
    ),
}


@dataclass(frozen=True, slots=True)
class HtmxTimingHeaderError(RuntimeError):
    """Internal fail-loud boundary for response headers removed by htmx 4."""

    header: str
    version: str
    helper: str
    lifecycle_event: str

    def __str__(self) -> str:
        return (
            f"{self.header} is unsupported by provisioned htmx {self.version}; "
            f"{self.helper} is an htmx 2/generic wire helper. For htmx 4, render "
            f"event data into the target's HTML and read it from an external "
            f"{self.lifecycle_event} listener. The response was rejected before send."
        )


def enforce_htmx_response_compatibility(
    response: Any,
    *,
    manifest: HtmxProvisioningManifest | None,
    is_htmx_request: bool,
) -> Any:
    """Reject removed timing headers only for a proven managed htmx 4 request."""
    if manifest is None or manifest.tier != "4-preview":
        return response
    headers = getattr(response, "headers", ())
    for name, _value in headers:
        removed = _REMOVED_TIMING_HEADERS.get(name.lower())
        if removed is None:
            continue
        if not is_htmx_request:
            with_vary = getattr(response, "with_vary", None)
            return with_vary("HX-Request", "HX-Request-Type") if callable(with_vary) else response
        helper, lifecycle_event = removed
        canonical = "HX-" + "-".join(part.capitalize() for part in name.split("-")[1:])
        raise HtmxTimingHeaderError(canonical, manifest.version, helper, lifecycle_event)
    return response


def htmx_manifest_snippet(manifest: HtmxProvisioningManifest, *, nonce: str = "") -> str:
    """Render an ordered managed bundle from a freeze-time manifest."""
    nonce_attr = f' nonce="{html.escape(nonce, quote=True)}"' if nonce else ""
    tags: list[str] = []
    policy = manifest.client_policy
    if policy is not None:
        config = {
            "noSwap": list(policy.no_swap_statuses),
            "defaultTimeout": policy.default_timeout_ms,
            "compat": {"swapErrorResponseCodes": policy.compat_swap_error_responses},
        }
        content = html.escape(json.dumps(config, separators=(",", ":")), quote=True)
        tags.append(
            f'<meta name="htmx-config" content="{content}" data-chirp="htmx-config"'
            f' data-chirp-htmx-tier="{manifest.tier}"'
            f' data-chirp-htmx-version="{html.escape(manifest.version, quote=True)}">'
        )
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
