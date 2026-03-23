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


def alpine_snippet(version: str, csp: bool = False) -> str:
    """Build the full Alpine.js injection block.

    Includes plugins (Mask, Intersect, Focus), the ``safeData`` helper with
    chirp-ui store init, and the Alpine.js core script.

    Args:
        version: Alpine version (e.g. "3.15.8").
        csp: If True, use the CSP-safe build for strict Content-Security-Policy.

    Returns:
        HTML: safeData helper + plugins + Alpine.js script tag.
    """
    pkg = "alpinejs" if not csp else "alpinejs/dist/cdn/csp"
    script = (
        f'<script defer src="{_CDN}/{pkg}@{version}" data-chirp="alpine"></script>'
    )
    return SAFE_DATA_HELPER + PLUGINS + script
