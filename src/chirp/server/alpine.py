"""Alpine.js script injection — single-authority Alpine for all Chirp apps.

Chirp is the sole injector of Alpine.js.  ``use_chirp_ui()`` auto-enables
``alpine=True``, so chirp-ui's ``app_shell_layout.html`` does **not** ship
its own Alpine scripts.

Injects before ``</body>`` via ``AlpineInject`` (dedup-aware ``HTMLInject``
subclass) when ``AppConfig(alpine=True)``.  Includes:

* All plugins (Mask, Intersect, Focus)
* Store init (modals, trays) for chirp-ui components
* ``Alpine.safeData(name, factory)`` helper — htmx-safe ``Alpine.data()``
  that works on full page loads *and* boosted navigation swaps.

Uses ``defer`` so Alpine runs after DOM parsing; Alpine 3 auto-discovers
elements including those swapped by htmx.
"""

import json
from typing import Any

from kida.template import Markup

_CDN = "https://cdn.jsdelivr.net/npm"

PLUGINS = (
    f'<script defer src="{_CDN}/@alpinejs/mask@3.14.0/dist/cdn.min.js" '
    'data-chirp="alpine-mask"></script>'
    f'<script defer src="{_CDN}/@alpinejs/intersect@3.14.0/dist/cdn.min.js" '
    'data-chirp="alpine-intersect"></script>'
    f'<script defer src="{_CDN}/@alpinejs/focus@3.14.0/dist/cdn.min.js" '
    'data-chirp="alpine-focus"></script>'
)

SAFE_DATA_HELPER = """<script>
(function(){
  var q=[];
  window._chirpAlpineData=function(n,f){
    if(window.Alpine&&Alpine.version){Alpine.data(n,f);}else{q.push([n,f]);}
  };
  document.addEventListener("alpine:init",function(){
    Alpine.store("modals",{});
    Alpine.store("trays",{});
    Alpine.safeData=function(n,f){Alpine.data(n,f);};
    q.forEach(function(r){Alpine.data(r[0],r[1]);});q=[];
  });
})();
</script>
"""


def _html_escape_attr(value: str) -> str:
    return (
        value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
    )


def alpine_json_config(dom_id: str, data: Any) -> Markup:
    """Emit a ``<script type="application/json">`` tag for Alpine component config.

    Provides a safe bridge for passing server-side data to client-side Alpine
    components without HTML attribute quoting issues. Registered as a template
    global when ``AppConfig(alpine=True)``.

    Args:
        dom_id: ``id`` attribute for the script tag. Used to locate and parse the
            config via ``document.getElementById(...).textContent``.
        data: Python value to serialize as JSON. Uses :func:`json.dumps` with
            ``default=str`` for non-JSON-serializable types.

    Returns:
        Markup safe for embedding; not double-escaped by the autoescaper.
    """
    json_str = json.dumps(data, default=str)
    json_str = json_str.replace("</", "<\\/")
    escaped_id = _html_escape_attr(dom_id)
    return Markup(f'<script id="{escaped_id}" type="application/json">{json_str}</script>')


def alpine_snippet(version: str, csp: bool = False) -> str:
    """Build the full Alpine.js injection block.

    Includes plugins (Mask, Intersect, Focus), the ``safeData`` helper with
    chirp-ui store init, and the Alpine.js core script.

    The script URL must include ``/dist/cdn.min.js``. A bare ``alpinejs@version``
    path on jsdelivr resolves to ``package.json`` ``main`` (``dist/module.cjs.js``),
    which is CommonJS and throws ``ReferenceError: module is not defined`` in the
    browser when loaded as a classic script.

    Args:
        version: Alpine version (e.g. "3.15.8").
        csp: If True, use the ``@alpinejs/csp`` browser CDN build (also explicit
            ``dist/cdn.min.js``; that package's main is CJS too).

    Returns:
        HTML: safeData helper + plugins + Alpine.js script tag.
    """
    if csp:
        path = f"@alpinejs/csp@{version}/dist/cdn.min.js"
    else:
        path = f"alpinejs@{version}/dist/cdn.min.js"
    script = f'<script defer src="{_CDN}/{path}" data-chirp="alpine"></script>'
    return SAFE_DATA_HELPER + PLUGINS + script
