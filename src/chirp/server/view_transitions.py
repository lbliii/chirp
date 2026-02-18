"""View Transitions bridge — one-flag setup for the View Transitions API.

Enables smooth, animated page transitions for both browser-native MPA
navigations and htmx-driven SPA-style swaps.  Two snippets are injected:

**Head snippet** (before ``</head>``):

- ``<meta name="view-transition" content="same-origin">`` — enables the
  browser's native cross-document View Transitions API.
- ``@view-transition { navigation: auto; }`` — CSS at-rule that opts the
  page into automatic cross-document transitions.
- Default crossfade keyframes (``chirp-vt-out`` / ``chirp-vt-in``) on the
  ``root`` transition name.  Apps can override with their own
  ``view-transition-name`` CSS for per-element transitions.

**Script snippet** (before ``</body>``):

- Sets ``htmx.config.globalViewTransitions = true`` so every htmx swap
  automatically uses the View Transitions API when available.
- Idempotent guard (``window.__chirpViewTransitions``) prevents double-init.
- Deferred listener (``htmx:load``) handles the case where htmx loads
  after the script (e.g., ``<script defer>``).

Injected into full-page HTML responses via ``HTMLInject`` middleware.
Controlled by ``AppConfig(view_transitions=True)`` (default: ``False``).
"""

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
