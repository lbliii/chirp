"""View Transitions bridge — tiered setup for the View Transitions API.

Three modes controlled by ``AppConfig.view_transitions``:

- ``False`` / ``"off"`` — inject nothing (default).
- ``True`` / ``"htmx"`` — inject only the **script snippet** so htmx swaps
  animate via the same-document View Transitions API (baseline in all
  browsers since October 2025).
- ``"full"`` — inject both the **head snippet** (MPA cross-document
  transitions) and the **script snippet**.  Cross-document transitions
  are not yet baseline (no Firefox support as of early 2026).

**Head snippet** (``"full"`` only, before ``</head>``):

- ``<meta name="view-transition" content="same-origin">`` — enables the
  browser's native cross-document View Transitions API.
- ``@view-transition { navigation: auto; }`` — CSS at-rule that opts the
  page into automatic cross-document transitions.
- Default crossfade keyframes (``chirp-vt-out`` / ``chirp-vt-in``) on the
  ``root`` transition name.  Apps can override with their own
  ``view-transition-name`` CSS for per-element transitions.

**Script snippet** (``"htmx"`` and ``"full"``, before ``</body>``):

- Sets ``htmx.config.globalViewTransitions = true`` so every htmx swap
  automatically uses the View Transitions API when available.
- Idempotent guard (``window.__chirpViewTransitions``) prevents double-init.
- Deferred listener (``htmx:load``) handles the case where htmx loads
  after the script (e.g., ``<script defer>``).

Injected into full-page HTML responses via ``HTMLInject`` middleware.
"""

from __future__ import annotations

VIEW_TRANSITIONS_CSS = """\
@view-transition { navigation: auto; }
::view-transition-old(root) { animation: chirp-vt-out 0.15s ease-out; }
::view-transition-new(root) { animation: chirp-vt-in 0.2s ease-in; }
@keyframes chirp-vt-out { from { opacity: 1; } to { opacity: 0; } }
@keyframes chirp-vt-in { from { opacity: 0; } to { opacity: 1; } }
"""

VIEW_TRANSITIONS_HEAD_SNIPPET = (
    '<meta name="view-transition" content="same-origin">'
    '<style data-chirp="view-transitions">' + VIEW_TRANSITIONS_CSS + "</style>"
)

VIEW_TRANSITIONS_JS = """\
(function(){
  if(window.__chirpViewTransitions)return;
  window.__chirpViewTransitions=true;
  function enable(){
    if(typeof htmx!=="undefined"){htmx.config.globalViewTransitions=true;}
  }
  enable();
  document.addEventListener("htmx:load",enable,{once:true});
})();
"""

VIEW_TRANSITIONS_SCRIPT_SNIPPET = (
    '<script data-chirp="view-transitions">' + VIEW_TRANSITIONS_JS + "</script>"
)


# ---------------------------------------------------------------------------
# Mode normalizer
# ---------------------------------------------------------------------------

ViewTransitionMode = str  # "off" | "htmx" | "full"


def normalize_view_transitions(value: bool | str) -> ViewTransitionMode:
    """Canonicalize the ``view_transitions`` config value.

    Returns one of ``"off"``, ``"htmx"``, or ``"full"``.
    """
    if value is False or value == "off":
        return "off"
    if value is True or value == "htmx":
        return "htmx"
    if value == "full":
        return "full"
    msg = f"Invalid view_transitions value: {value!r}. Use False, True, 'off', 'htmx', or 'full'."
    raise ValueError(msg)
