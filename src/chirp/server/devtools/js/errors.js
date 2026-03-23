// --- errors.js — Error handlers, pattern warnings, shortcuts, API, boot ---

// DRY: register an HTMX error event handler
function htmxErrorHandler(evtName, titleText, color, bodyFn, useCfg) {
  document.body.addEventListener(evtName, function(evt) {
    var d = evt.detail || {};
    var cfg = useCfg && d.elt ? formatConfig(getEffectiveConfig(d.elt)) : "";
    var body = bodyFn(d);
    addError(titleText, body, cfg);
    toast(titleText, body, color, cfg);
  });
}

htmxErrorHandler("htmx:targetError", "Target Not Found", COLORS.error, function(d) {
  var target = d.target || "(unknown selector)";
  var trigger = desc(d.elt || {});
  return target + "\nTriggered by " + trigger +
    "\n\nCommon cause: target is in a different fragment than the form. " +
    "Co-locate the target with the mutating element (e.g. put the result div inside the same HTMX-loaded content).";
}, true);

htmxErrorHandler("htmx:responseError", "Response Error", COLORS.error, function(d) {
  var xhr = d.xhr || {};
  return (xhr.status || "?") + " " + ((d.pathInfo && d.pathInfo.requestPath) || "");
}, true);

htmxErrorHandler("htmx:sendError", "Network Error", COLORS.error, function(d) {
  return ((d.pathInfo && d.pathInfo.requestPath) || "") + "\nIs the server running?";
}, true);

htmxErrorHandler("htmx:swapError", "Swap Error", COLORS.warning, function(d) {
  return String(d.error || "(unknown)");
}, true);

htmxErrorHandler("htmx:timeout", "Timeout", COLORS.warning, function(d) {
  return (d.pathInfo && d.pathInfo.requestPath) || "";
}, false);

htmxErrorHandler("htmx:onLoadError", "Load Handler Error", COLORS.warning, function(d) {
  return String(d.error || "(unknown)");
}, false);

// --- Pattern warnings ---
function getEffectiveSelect(startElt) {
  var node = startElt;
  while (node && node !== document.body) {
    var disinherit = node.getAttribute && node.getAttribute("hx-disinherit");
    if (disinherit && (/\bhx-select\b/.test(disinherit) || disinherit.trim() === "*")) return null;
    var s = node.getAttribute && node.getAttribute("hx-select");
    if (s) return s.trim();
    node = node.parentElement;
  }
  return null;
}

document.body.addEventListener("htmx:beforeSwap", function(evt) {
  var d = evt.detail || {};
  var xhr = d.xhr;
  var elt = d.elt;
  if (!xhr || !xhr.responseText || !elt) return;
  var sel = getEffectiveSelect(elt);
  if (!sel || typeof sel !== "string") return;
  sel = sel.trim();
  if (sel.indexOf("#") !== 0 || sel.indexOf(" ") >= 0) return;
  var id = sel.slice(1);
  if (!id) return;
  var re = new RegExp("id\\s*=\\s*[\"']" + id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "[\"']");
  if (!re.test(xhr.responseText)) {
    toast("Empty hx-select", "Response has no element matching " + sel + ". Inherited hx-select may yield blank swap.", COLORS.warning);
  }
});

document.body.addEventListener("htmx:configRequest", function(evt) {
  var d = evt.detail || {};
  var elt = d.elt;
  var path = (d.pathInfo && d.pathInfo.requestPath) || "";
  if (!elt) return;

  function getEffectiveTarget() {
    var node = elt;
    while (node && node !== document.body) {
      var disinherit = node.getAttribute && node.getAttribute("hx-disinherit");
      if (disinherit && /hx-target/.test(disinherit)) return null;
      var t = node.getAttribute && node.getAttribute("hx-target");
      if (t) return t.trim();
      node = node.parentElement;
    }
    return null;
  }

  var target = getEffectiveTarget();
  var trigger = (elt.getAttribute && elt.getAttribute("hx-trigger")) || "";
  var isLoadTrigger = /(^|[\s,])load(\s|,|$)/.test(trigger);

  if (isLoadTrigger && target && /#main|#page-content/.test(target)) {
    toast("Load-trigger targets #main", "hx-trigger=\"load\" will replace the page on load. Use fragment_island or hx-target=\"this\".", COLORS.warning);
  }

  var method = (elt.getAttribute && elt.getAttribute("hx-post")) ? "post" :
    (elt.getAttribute && elt.getAttribute("hx-put")) ? "put" :
    (elt.getAttribute && elt.getAttribute("hx-patch")) ? "patch" :
    (elt.getAttribute && elt.getAttribute("hx-delete")) ? "delete" :
    (elt.getAttribute && elt.getAttribute("method")) === "post" ? "post" : null;
  if (!method || method === "get") return;
  var hasExplicitTarget = elt.getAttribute && elt.getAttribute("hx-target");
  if (!hasExplicitTarget) {
    var ancestor = elt.closest && elt.closest("[hx-target]");
    if (ancestor && /#main|#page-content/.test(ancestor.getAttribute("hx-target") || "")) {
      toast("Broad inherited target", "Mutating request to " + path + " inherits broad target. Use fragment_island or explicit hx-target.", COLORS.warning);
    }
  }
});

// --- Keyboard shortcuts ---
document.addEventListener("keydown", function(e) {
  if (e.key === "Escape") {
    if (state.inspector) { stopInspector(); state.inspector = false; e.preventDefault(); return; }
    if (state.open) { state.open = false; drawer.classList.remove("open"); saveState(); e.preventDefault(); }
    return;
  }
  if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === "d" || e.key === "D")) {
    e.preventDefault();
    renderPanel();
    toggleDrawer();
  }
  if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === "k" || e.key === "K")) {
    e.preventDefault();
    renderPanel();
    if (!state.open) {
      state.open = true;
      if (drawer) drawer.classList.add("open");
      saveState();
      updatePill();
    }
    toggleInspector();
  }
});

// --- Public API ---
var CH = (window.ChirpHtmxDebug = window.ChirpHtmxDebug || {});
CH.version = 3;
CH.getState = function() { return state; };
CH.exportRecordsJson = function() {
  return JSON.stringify({
    records: state.records,
    errors: state.errors,
    sseConnections: state.sseConnections,
    sseEvents: state.sseEvents,
    vtEvents: state.vtEvents,
  }, null, 2);
};
CH.getSSEConnections = function() { return state.sseConnections; };
CH.getViewTransitions = function() { return state.vtEvents; };

// --- Boot ---
function boot() {
  renderPanel();
  if (state.open) drawer.classList.add("open");
  updatePill();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}

try {
  if (localStorage.getItem(STORAGE_KEYS.verbose) === "1") {
    console.log("\u2301\u2301 chirp devtools active (v3 \u2014 sse, waterfall, vt, diff, render plan, highlight)");
  }
} catch (err) {}
