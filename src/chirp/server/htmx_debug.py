"""HTMX debug bootstrap assets for development mode.

The app injects a single script tag on full-page responses. The script itself
is served from an internal route and is idempotent, so it can be included on
multiple navigations without duplicating listeners or toast containers.
"""

HTMX_DEBUG_BOOT_PATH = "/__chirp/debug/htmx.js"

HTMX_DEBUG_BOOT_SNIPPET = (
    f'<script src="{HTMX_DEBUG_BOOT_PATH}" data-chirp-debug="htmx" defer></script>'
)

HTMX_DEBUG_BOOT_JS = """\
(function() {
  if (window.__chirpHtmxDebugBooted) return;
  window.__chirpHtmxDebugBooted = true;

  function desc(el) {
    if (!el || !el.tagName) return "(unknown element)";
    var tag = "<" + el.tagName.toLowerCase() + ">";
    var id = el.id ? ("#" + el.id) : "";
    return tag + id;
  }

  function getToastBox() {
    var existing = document.getElementById("chirp-htmx-debug-toasts");
    if (existing) return existing;
    var box = document.createElement("div");
    box.id = "chirp-htmx-debug-toasts";
    box.setAttribute(
      "style",
      "position:fixed;bottom:16px;right:16px;z-index:99999;" +
      "display:flex;flex-direction:column-reverse;gap:8px;" +
      "max-height:60vh;overflow-y:auto;pointer-events:none;"
    );
    document.body.appendChild(box);
    return box;
  }

  function toast(title, body, color) {
    var box = getToastBox();
    var el = document.createElement("div");
    el.setAttribute(
      "style",
      "pointer-events:auto;background:#1a1b26;color:#a9b1d6;" +
      "border:1px solid " + color + ";border-left:4px solid " + color + ";" +
      "border-radius:6px;padding:10px 14px;max-width:420px;font-size:13px;"
    );
    el.innerHTML =
      "<div style='color:" + color + ";font-weight:bold;margin-bottom:4px'>" +
      title + "</div><div style='white-space:pre-wrap'>" + body + "</div>";
    el.addEventListener("click", function() { el.remove(); });
    box.appendChild(el);
    setTimeout(function() { el.remove(); }, 12000);
  }

  document.body.addEventListener("htmx:targetError", function(evt) {
    var d = evt.detail || {};
    var target = d.target || "(unknown selector)";
    var trigger = desc(d.elt || evt.target);
    console.warn("htmx:targetError", { target: target, trigger: trigger });
    toast("Target Not Found", target + "\\nTriggered by " + trigger, "#f7768e");
  });

  document.body.addEventListener("htmx:responseError", function(evt) {
    var d = evt.detail || {};
    var xhr = d.xhr || {};
    var status = xhr.status || "?";
    var path = d.pathInfo ? (d.pathInfo.requestPath || "") : "";
    console.warn("htmx:responseError", { status: status, path: path, detail: d });
    toast("Response Error", String(status) + " " + path, "#f7768e");
  });

  document.body.addEventListener("htmx:sendError", function(evt) {
    var d = evt.detail || {};
    var path = d.pathInfo ? (d.pathInfo.requestPath || "") : "";
    console.warn("htmx:sendError", { path: path, detail: d });
    toast("Network Error", path + "\\nIs the server running?", "#f7768e");
  });

  document.body.addEventListener("htmx:swapError", function(evt) {
    var d = evt.detail || {};
    console.warn("htmx:swapError", d);
    toast("Swap Error", String(d.error || "(unknown)"), "#e0af68");
  });

  document.body.addEventListener("htmx:timeout", function(evt) {
    var d = evt.detail || {};
    var path = d.pathInfo ? (d.pathInfo.requestPath || "") : "";
    console.warn("htmx:timeout", d);
    toast("Timeout", path, "#e0af68");
  });

  document.body.addEventListener("htmx:onLoadError", function(evt) {
    var d = evt.detail || {};
    console.warn("htmx:onLoadError", d);
    toast("Load Handler Error", String(d.error || "(unknown)"), "#e0af68");
  });

  console.log("chirp htmx debug overlay active");
})();
"""
