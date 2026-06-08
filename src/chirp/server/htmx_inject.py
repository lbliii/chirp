"""htmx script injection — single-authority htmx for all Chirp apps.

Chirp is the sole injector of htmx when ``AppConfig(htmx=True)``. The script is
inserted before ``</body>`` via :class:`~chirp.middleware.inject.HtmxInject`
(a dedup-aware ``HTMLInject`` subclass) and emits a ``data-chirp="htmx"`` marker
so a page that already ships htmx is left untouched.

Uses the proven unpkg browser builds (the same URLs the ``chirp new`` chirpui
scaffold ships):

* ``https://unpkg.com/htmx.org@{version}`` — the IIFE build that defines the
  global ``window.htmx``. It must stay a classic blocking script: no
  ``type="module"`` (which would scope htmx away from the global) and no
  ``defer`` games beyond what htmx itself expects.
* ``https://unpkg.com/htmx-ext-sse@{sse_version}/sse.js`` — the SSE extension,
  appended only when ``AppConfig(htmx_sse=True)``.

Unlike Alpine (jsDelivr, where a bare ``alpinejs@version`` resolves to a broken
CommonJS module), unpkg's ``htmx.org@VER`` *is* the browser build, so no
``/dist/...`` subpath is required. Do **not** swap this to a jsDelivr bare npm
path — that is the documented CDN footgun.
"""

import re

# htmx ships proven browser builds from unpkg (NOT jsDelivr — see module docs).
_CDN = "https://unpkg.com"

# Pinned SSE extension version — matches the chirpui scaffold (sse.js@2.2.2).
SSE_EXTENSION_VERSION = "2.2.2"

# Robust dedup heuristic: an htmx <script src="..."> already on the page. Mirrors
# ``rules_htmx_provisioning._HTMX_SCRIPT`` so a marker-less, hand-provisioned or
# third-party htmx script (e.g. ``<script src=".../htmx.min.js">``) is detected
# and ``HtmxInject`` skips injection instead of double-loading the runtime. Any
# src URL containing 'htmx' counts (unpkg, jsDelivr, self-hosted bundles).
_HTMX_SCRIPT = re.compile(
    r"""<script\b[^>]*\bsrc\s*=\s*["'][^"']*htmx[^"']*["']""",
    re.IGNORECASE,
)


def htmx_already_present(body: str) -> bool:
    """Return True if *body* already provisions htmx.

    Two signals count: Chirp's own ``data-chirp="htmx"`` dedup marker, or any
    htmx ``<script src="...htmx...">`` (marker-less hand-provisioned or
    third-party). Used by :class:`~chirp.middleware.inject.HtmxInject` to avoid
    double-loading the runtime.
    """
    return 'data-chirp="htmx"' in body or _HTMX_SCRIPT.search(body) is not None


def htmx_snippet(version: str, sse: bool = False) -> str:
    """Build the htmx injection block.

    Args:
        version: htmx core version (e.g. "2.0.4"). Threaded straight into the
            unpkg URL.
        sse: If True, also append the htmx SSE extension (``htmx-ext-sse``).

    Returns:
        HTML: the htmx core ``<script>`` tag (carrying the ``data-chirp="htmx"``
        dedup marker) followed by the SSE extension tag when *sse* is True.
    """
    core = f'<script src="{_CDN}/htmx.org@{version}" data-chirp="htmx"></script>'
    if not sse:
        return core
    sse_ext = (
        f'<script src="{_CDN}/htmx-ext-sse@{SSE_EXTENSION_VERSION}/sse.js" '
        f'data-chirp="htmx-sse"></script>'
    )
    return core + sse_ext
