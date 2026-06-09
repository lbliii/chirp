"""htmx script injection — opt-in single-authority htmx for Chirp apps.

Mirrors the Alpine injection path (``src/chirp/server/alpine.py``). When
``AppConfig(htmx=True)`` Chirp injects the htmx core ``<script>`` before
``</body>`` via :class:`~chirp.middleware.inject.StreamingHTMLInject`, dedup-aware
on ``data-chirp="htmx"`` so a document that already ships htmx (chirp-ui
``shell.html``/``boost.html``, the v2 scaffold) is left untouched.

CDN footgun (mirrors Alpine): the script ``src`` **must** use the explicit
jsDelivr ``/dist/htmx.min.js`` path. The framework convention is jsDelivr; the
hardcoded chirp-ui/scaffold tags use unpkg, which is why dedup matters once a
template ships its own tag.

The htmx core is an external ``src=`` script, but it still accepts the live
per-request CSP nonce: under a strict nonce-only ``script-src 'nonce-...'`` an
external ``<script src>`` without the nonce is blocked, so the snippet factory
threads the nonce onto the tag the same way the Alpine bootstrap does.
"""

_CDN = "https://cdn.jsdelivr.net/npm"


def htmx_snippet(version: str, *, nonce: str = "") -> str:
    """Build the htmx core injection ``<script>`` tag.

    The script URL uses the explicit ``/dist/htmx.min.js`` path — the framework's
    CDN convention (the same explicit-``/dist`` rule ``rules_alpine_cdn`` enforces
    for Alpine). Unlike Alpine — whose bare jsDelivr path resolves to a CommonJS
    module that throws in the browser — htmx's package ``main`` is browser-safe,
    so for htmx this is a consistency/minification choice rather than a fix for a
    hard failure; pinning ``/dist/htmx.min.js`` keeps every framework CDN URL on
    the explicit minified browser bundle.

    Args:
        version: htmx version (e.g. "2.0.4").
        nonce: When non-empty, the ``<script>`` carries a ``nonce="..."``
            attribute so it survives a nonce-based CSP that no longer ships
            ``'unsafe-inline'`` / loads only nonced scripts.

    Returns:
        The htmx core ``<script defer src=...>`` tag marked
        ``data-chirp="htmx"`` for dedup.
    """
    nonce_attr = f' nonce="{nonce}"' if nonce else ""
    return (
        f'<script defer src="{_CDN}/htmx.org@{version}/dist/htmx.min.js"'
        f'{nonce_attr} data-chirp="htmx"></script>'
    )
