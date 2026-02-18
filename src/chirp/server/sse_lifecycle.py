"""SSE lifecycle bridge — connection status for ``[sse-connect]`` elements.

htmx's SSE extension creates an ``EventSource`` internally but doesn't
surface connection lifecycle to the DOM in a way that's easy to style
or hook into.  This script bridges that gap.

On every ``htmx:sseOpen`` and ``htmx:sseError`` event, it updates a
``data-sse-state`` attribute on the ``[sse-connect]`` element:

- ``"connected"`` — EventSource is open
- ``"disconnected"`` — EventSource errored or closed

This enables pure-CSS connection indicators::

    [data-sse-state="disconnected"] .sse-indicator { display: block; }
    [data-sse-state="connected"] .sse-indicator { display: none; }

It also dispatches ``chirp:sse:connected`` and ``chirp:sse:disconnected``
custom events on the element for JS hooks.

Injected into full-page HTML responses via ``HTMLInject`` middleware.
Controlled by ``AppConfig(sse_lifecycle=True)`` (default: ``True``).
"""

SSE_LIFECYCLE_JS = """\
(function(){
  if(window.__chirpSSELifecycle)return;
  window.__chirpSSELifecycle=true;
  function setState(el,state){
    el.setAttribute("data-sse-state",state);
    el.dispatchEvent(new CustomEvent("chirp:sse:"+state,{bubbles:true}));
  }
  document.body.addEventListener("htmx:sseOpen",function(evt){
    var el=evt.target.closest("[sse-connect]");
    if(el)setState(el,"connected");
  });
  document.body.addEventListener("htmx:sseError",function(evt){
    var el=evt.target.closest("[sse-connect]");
    if(el)setState(el,"disconnected");
  });
  document.body.addEventListener("htmx:sseClose",function(evt){
    var el=evt.target.closest("[sse-connect]");
    if(el)setState(el,"disconnected");
  });
})();
"""

SSE_LIFECYCLE_SNIPPET = '<script data-chirp="sse-lifecycle">' + SSE_LIFECYCLE_JS + "</script>"
