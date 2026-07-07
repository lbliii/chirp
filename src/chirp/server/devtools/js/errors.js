// --- errors.js — Error handlers, pattern warnings, shortcuts, API, boot ---

var seenHtmxErrors = typeof WeakSet !== "undefined" ? new WeakSet() : null;

function firstHtmxError(detail) {
  var token = (detail && (detail.ctx || detail.xhr)) || detail;
  if (!seenHtmxErrors || !token || typeof token !== "object") return true;
  if (seenHtmxErrors.has(token)) return false;
  seenHtmxErrors.add(token);
  return true;
}

// DRY: register an HTMX 2/4 error event handler
function htmxErrorHandler(evtNames, titleText, color, bodyFn, useCfg) {
  if (typeof evtNames === "string") evtNames = [evtNames];
  onHtmxEvents(evtNames, function(evt) {
    var d = evt.detail || {};
    if (!firstHtmxError(d)) return;
    var source = htmxSource(d);
    var cfg = useCfg && source ? formatConfig(getEffectiveConfig(source)) : "";
    var body = bodyFn(d);
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

htmxErrorHandler(["htmx:responseError", "htmx:response:error"], "Response Error", COLORS.error, function(d) {
  var ctx = htmxContext(d);
  var response = htmxResponse(d) || {};
  var status = (ctx.response && ctx.response.status) || response.status || "?";
  return status + " " + (htmxRequest(d).action || (d.pathInfo && d.pathInfo.requestPath) || "");
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

onHtmxEvents(["htmx:error"], function(evt) {
  var d = evt.detail || {};
  if (!firstHtmxError(d)) return;
  var ctx = htmxContext(d);
  var error = d.error || ctx.error || {};
  var message = String(error.message || error || "Request failed");
  var lower = message.toLowerCase();
  var title = "Network Error";
  var color = COLORS.error;
  if (lower.indexOf("timeout") >= 0) {
    title = "Timeout";
    color = COLORS.warning;
  } else if (lower.indexOf("target") >= 0 || lower.indexOf("selector") >= 0) {
    title = "Target Not Found";
  } else if (lower.indexOf("swap") >= 0 || lower.indexOf("dom") >= 0) {
    title = "Swap Error";
    color = COLORS.warning;
  }
  var source = htmxSource(d);
  var cfg = source ? formatConfig(getEffectiveConfig(source)) : "";
  var path = htmxRequest(d).action || "";
  var body = message + (path ? "\n" + path : "");
  toast(title, body, color, cfg);
});

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

onHtmxEventPair(["htmx:beforeSwap", "htmx:before:swap"], function(evt) {
  var d = evt.detail || {};
  var ctx = htmxContext(d);
  var responseText = ctx.text != null ? ctx.text : (d.xhr && d.xhr.responseText);
  var swapTarget = ctx.target || d.elt;
  var trigger = htmxSource(d) || swapTarget;
  if (!responseText || !trigger) return;
  var sel = getEffectiveSelect(trigger);
  if (!sel || typeof sel !== "string") return;
  sel = sel.trim();
  if (sel.indexOf("#") !== 0 || sel.indexOf(" ") >= 0) return;
  var id = sel.slice(1);
  if (!id) return;
  var re = new RegExp("id\\s*=\\s*[\"']" + id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "[\"']");
  if (!re.test(responseText)) {
    toast("Empty hx-select", "Response has no element matching " + sel + ". Inherited hx-select may yield blank swap.", COLORS.warning);
  }
});

onHtmxEventPair(["htmx:configRequest", "htmx:config:request"], function(evt) {
  var d = evt.detail || {};
  var elt = htmxSource(d);
  var path = htmxRequest(d).action || (d.pathInfo && d.pathInfo.requestPath) || "";
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
CH.help = function() {
  return {
    enabledBy: "AppConfig(debug=True) or chirp dev app:app",
    drawer: "Press Ctrl+Shift+D to toggle the Chirp DevTools drawer.",
    inspector: "Press Ctrl+Shift+K to inspect effective hx-* attributes.",
    exportRecordsJson: "Call window.ChirpHtmxDebug.exportRecordsJson() for agent-readable htmx, transition, SSE, View Transition, render-plan, and Swap Doctor records.",
    transitionCoverage: "Call window.ChirpHtmxDebug.transitionCoverage(['normal', 'boosted', 'targeted']) to report observed and intentionally untested request modes.",
    getState: "Call window.ChirpHtmxDebug.getState() for the live in-browser state object.",
    verboseBootLog: "Set localStorage['chirp-debug-verbose']='1' before reload to log boot.",
  };
};
CH.exportRecordsJson = function() {
  return JSON.stringify({
    records: state.records,
    errors: state.errors,
    historyEvents: state.historyEvents,
    sseConnections: state.sseConnections,
    sseEvents: state.sseEvents,
    transitionTraces: state.transitionTraces,
    transitionCoverage: buildTransitionCoverage([]),
    vtEvents: state.vtEvents,
  }, null, 2);
};
CH.getSSEConnections = function() { return state.sseConnections; };
CH.getViewTransitions = function() { return state.vtEvents; };
CH.transitionCoverage = function(expectedModes) { return buildTransitionCoverage(expectedModes || []); };

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
