"""Alpine.js script injection — opt-in local UI state support.

Injects the Alpine.js script before ``</body>`` when ``AppConfig(alpine=True)``.
Also injects modals/trays store init so chirp-ui modal_overlay and tray work
without extending app_shell_layout.

Uses ``defer`` so Alpine runs after DOM parsing; Alpine 3 auto-discovers
elements including those swapped by htmx.

Controlled by ``AppConfig(alpine=True)`` (default: ``False``).
"""

CHIRPUI_STORE_INIT = """<script>
document.addEventListener("alpine:init",function(){
  Alpine.store("modals",{});
  Alpine.store("trays",{});
  Alpine.effect(function(){
    var any=Object.values(Alpine.store("modals")).some(Boolean)||Object.values(Alpine.store("trays")).some(Boolean);
    document.body.style.overflow=any?"hidden":"";
  });
});
</script>
"""


def alpine_snippet(version: str, csp: bool = False) -> str:
    """Build the Alpine.js script tag and chirp-ui store init for injection.

    Includes modals/trays store init so modal_overlay and tray work in any
    Chirp app with alpine=True.

    Args:
        version: Alpine version (e.g. "3.15.8").
        csp: If True, use the CSP-safe build for strict Content-Security-Policy.

    Returns:
        HTML: store init script + Alpine.js script tag.
    """
    pkg = "alpinejs" if not csp else "alpinejs/dist/cdn/csp"
    script = f'<script defer src="https://unpkg.com/{pkg}@{version}" data-chirp="alpine"></script>'
    return CHIRPUI_STORE_INIT + script
