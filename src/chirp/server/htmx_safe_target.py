"""Safe target — auto-add hx-target="this" to event-driven elements.

When hx-boost sets hx-target on the <body>, that target propagates to
every child element via htmx's attribute inheritance.  Self-updating
elements (counters, badges, live regions) that use ``hx-trigger`` with
``from:`` to listen for server-sent events inherit this global target
and silently swap their tiny fragment response into the main content
area, wiping the page.

This script fixes the footgun automatically.  On every ``htmx:load``
(initial page load + after each swap), it finds elements that:

1. Listen for events from elsewhere (``hx-trigger`` contains ``from:``)
2. Make an HTTP request (``hx-get``, ``hx-post``, etc.)
3. Have **no** explicit ``hx-target``

…and adds ``hx-target="this"`` so the response targets the element
itself instead of the inherited layout target.

The attribute is visible in DevTools — it looks like the developer
wrote it.  If a developer sets ``hx-target`` explicitly, the
``:not([hx-target])`` selector skips the element.

Injected into every full-page HTML response via ``HTMLInject``
middleware.  Disabled with ``AppConfig(safe_target=False)``.
"""

SAFE_TARGET_JS = """\
(function(){
  if(typeof htmx==="undefined"||window.__chirpSafeTarget)return;
  window.__chirpSafeTarget=true;
  var SEL=[
    '[hx-trigger*="from:"][hx-get]:not([hx-target])',
    '[hx-trigger*="from:"][hx-post]:not([hx-target])',
    '[hx-trigger*="from:"][hx-put]:not([hx-target])',
    '[hx-trigger*="from:"][hx-patch]:not([hx-target])',
    '[hx-trigger*="from:"][hx-delete]:not([hx-target])'
  ].join(",");
  htmx.onLoad(function(root){
    var els=root.querySelectorAll?root.querySelectorAll(SEL):[];
    for(var i=0;i<els.length;i++){els[i].setAttribute("hx-target","this")}
  });
})();
"""


def safe_target_snippet(nonce: str = "") -> str:
    """Build the safe-target inline ``<script>``.

    When *nonce* is non-empty the ``<script>`` carries a ``nonce="..."``
    attribute so it survives a nonce-based CSP that no longer ships
    ``'unsafe-inline'``.
    """
    nonce_attr = f' nonce="{nonce}"' if nonce else ""
    return f'<script data-chirp="safe-target"{nonce_attr}>{SAFE_TARGET_JS}</script>'


#: Back-compat module constant (un-nonced). Prefer :func:`safe_target_snippet`.
SAFE_TARGET_SNIPPET = safe_target_snippet()
