// --- collectors.js — HTMX/SSE/VT event collectors ---

// DRY: shared SSE event push
function pushSseEvent(connId, type, url, data) {
  state.sseEvents.unshift({ connId: connId, type: type, url: url, ts: Date.now(), data: data });
  if (state.sseEvents.length > BUFFER_SIZE) state.sseEvents.pop();
  refreshSsePanel();
}

// --- SSE Monitor (monkey-patch EventSource) ---
var OriginalEventSource = window.EventSource;
if (OriginalEventSource) {
  window.EventSource = function ChirpTrackedEventSource(url, opts) {
    var es = new OriginalEventSource(url, opts);
    var conn = {
      id: "sse-" + Date.now() + "-" + Math.random().toString(36).slice(2),
      url: url,
      openedAt: null,
      closedAt: null,
      readyState: es.readyState,
      eventCount: 0,
      errorCount: 0,
      lastEventAt: null,
    };
    state.sseConnections.unshift(conn);
    if (state.sseConnections.length > 20) state.sseConnections.pop();

    es.addEventListener("open", function() {
      conn.openedAt = Date.now();
      conn.readyState = es.readyState;
      pushSseEvent(conn.id, "open", url, null);
    });

    es.addEventListener("error", function() {
      conn.errorCount++;
      conn.readyState = es.readyState;
      pushSseEvent(conn.id, "error", url, "readyState=" + es.readyState);
    });

    var origAddListener = es.addEventListener.bind(es);
    es.addEventListener = function(type, fn, opts2) {
      if (type !== "open" && type !== "error") {
        var wrapped = function(evt) {
          conn.eventCount++;
          conn.lastEventAt = Date.now();
          conn.readyState = es.readyState;
          var preview = evt.data ? String(evt.data).slice(0, 200) : "";
          pushSseEvent(conn.id, type, url, preview);
          return fn.call(es, evt);
        };
        return origAddListener(type, wrapped, opts2);
      }
      return origAddListener(type, fn, opts2);
    };

    var origOnMessage = null;
    Object.defineProperty(es, "onmessage", {
      get: function() { return origOnMessage; },
      set: function(fn) {
        origOnMessage = fn;
        origAddListener("message", function(evt) {
          conn.eventCount++;
          conn.lastEventAt = Date.now();
          conn.readyState = es.readyState;
          var preview = evt.data ? String(evt.data).slice(0, 200) : "";
          pushSseEvent(conn.id, "message", url, preview);
          if (fn) fn.call(es, evt);
        });
      },
    });

    var origClose = es.close.bind(es);
    es.close = function() {
      conn.closedAt = Date.now();
      conn.readyState = 2;
      pushSseEvent(conn.id, "close", url, null);
      return origClose();
    };

    return es;
  };
  window.EventSource.CONNECTING = 0;
  window.EventSource.OPEN = 1;
  window.EventSource.CLOSED = 2;
}

// --- View Transition tracking ---
if (document.startViewTransition) {
  var origStartVT = document.startViewTransition.bind(document);
  document.startViewTransition = function(cb) {
    var vtRecord = {
      id: "vt-" + Date.now() + "-" + Math.random().toString(36).slice(2),
      startedAt: Date.now(),
      readyAt: null,
      finishedAt: null,
      skipped: false,
    };
    state.vtEvents.unshift(vtRecord);
    if (state.vtEvents.length > 50) state.vtEvents.pop();

    var vt = origStartVT(cb);
    if (vt && vt.ready) {
      vt.ready.then(function() {
        vtRecord.readyAt = Date.now();
        refreshActivityPanel();
      }).catch(function() {
        vtRecord.skipped = true;
        refreshActivityPanel();
      });
    }
    if (vt && vt.finished) {
      vt.finished.then(function() {
        vtRecord.finishedAt = Date.now();
        refreshActivityPanel();
      }).catch(function() {
        vtRecord.skipped = true;
        refreshActivityPanel();
      });
    }
    return vt;
  };
}

// --- HTMX Event Collector ---
function findPendingRecord(hasSent, hasResponse) {
  for (var i = 0; i < state.records.length; i++) {
    var r = state.records[i];
    if (!!r.timing.sent !== hasSent) continue;
    if (!!r.timing.response !== hasResponse) continue;
    return r;
  }
  return null;
}

function createRecord() {
  var r = {
    id: "req-" + Date.now() + "-" + Math.random().toString(36).slice(2),
    path: "",
    method: "GET",
    target: "",
    swap: "innerHTML",
    status: null,
    timing: {},
    failed: false,
    error: null,
    isOob: false,
    elt: null,
    expanded: false,
    route: null,
    layout: null,
    requestId: null,
    requestHeaders: null,
    responseHeaders: null,
    hxPairs: null,
    renderIntent: "",
    bodyPreview: "",
    contentType: "",
    renderPlan: null,
    domBefore: null,
    domAfter: null,
    domDiff: null,
  };
  state.records.unshift(r);
  if (state.records.length > BUFFER_SIZE) state.records.pop();
  state.requestCount++;
  updatePill();
  return r;
}

document.body.addEventListener("htmx:configRequest", function(evt) {
  if (state.paused) return;
  var d = evt.detail || {};
  var r = createRecord();
  r.path = (d.pathInfo && d.pathInfo.requestPath) || "";
  r.method = (d.parameters && d.parameters["_method"]) || (d.elt && (
    d.elt.getAttribute("hx-post") ? "POST" :
    d.elt.getAttribute("hx-put") ? "PUT" :
    d.elt.getAttribute("hx-patch") ? "PATCH" :
    d.elt.getAttribute("hx-delete") ? "DELETE" : "GET"
  ));
  r.elt = d.elt;
  r.timing.config = Date.now();
  try {
    r.requestHeaders = {};
    if (d.headers && typeof d.headers === "object") {
      for (var hk in d.headers) {
        if (Object.prototype.hasOwnProperty.call(d.headers, hk)) {
          r.requestHeaders[hk] = d.headers[hk];
        }
      }
    }
  } catch (e) {
    r.requestHeaders = {};
  }
  firePlugin("onRequest", r);
});

document.body.addEventListener("htmx:beforeRequest", function(evt) {
  var r = findPendingRecord(false, false);
  if (r) r.timing.sent = Date.now();
});

document.body.addEventListener("htmx:afterRequest", function(evt) {
  var d = evt.detail || {};
  var r = findPendingRecord(true, false);
  if (!r) return;
  var xhr = d.xhr;
  if (xhr) {
    r.status = xhr.status;
    r.timing.response = Date.now();
    if (r.status >= 400) {
      r.failed = true;
      state.errorCount++;
    }
    var routeKind = xhr.getResponseHeader && xhr.getResponseHeader("X-Chirp-Route-Kind");
    if (routeKind) {
      r.route = {
        kind: routeKind,
        meta: xhr.getResponseHeader("X-Chirp-Route-Meta") || "",
        files: xhr.getResponseHeader("X-Chirp-Route-Files") || "",
        section: xhr.getResponseHeader("X-Chirp-Route-Section") || "",
        contextChain: xhr.getResponseHeader("X-Chirp-Context-Chain") || "",
        shellContext: xhr.getResponseHeader("X-Chirp-Shell-Context") || "",
      };
    }
    var layoutChain = xhr.getResponseHeader && xhr.getResponseHeader("X-Chirp-Layout-Chain");
    var layoutMatch = xhr.getResponseHeader && xhr.getResponseHeader("X-Chirp-Layout-Match");
    var layoutMode = xhr.getResponseHeader && xhr.getResponseHeader("X-Chirp-Layout-Mode");
    if (layoutChain || layoutMatch || layoutMode) {
      r.layout = {
        chain: layoutChain || "",
        match: layoutMatch || "",
        mode: layoutMode || "",
      };
    }
    var reqId = xhr.getResponseHeader && xhr.getResponseHeader("X-Request-Id");
    if (reqId) r.requestId = reqId;
    var rh = parseResponseHeaders(xhr);
    r.responseHeaders = rh;
    r.contentType = rh["content-type"] || "";
    r.renderIntent = rh["x-chirp-render-intent"] || "";
    r.hxPairs = filterHxAndChirpHeaders(rh);

    var rpHeader = xhr.getResponseHeader && xhr.getResponseHeader("X-Chirp-Render-Plan");
    if (rpHeader) {
      r.renderPlan = decodeRenderPlan(rpHeader);
    }

    if (xhr.responseText) {
      var txt = String(xhr.responseText);
      r.bodyPreview =
        txt.length > 4096
          ? txt.slice(0, 4096) + "\n\u2026 (truncated, " + txt.length + " bytes total)"
          : txt;
    }
    firePlugin("onResponse", r);
  }
});

document.body.addEventListener("htmx:beforeSwap", function(evt) {
  var d = evt.detail || {};
  var r = findPendingRecord(true, true);
  if (!r) return;
  var t = d.target;
  r.target = (t && t.id) ? "#" + t.id : (t && t.className && String(t.className).trim()) ? "." + String(t.className).split(/\s+/)[0] : (t ? "this" : "");
  r.swap = (d.swapStyle && d.swapStyle) || "innerHTML";
  r.timing.beforeSwap = Date.now();

  if (t) {
    try { r.domBefore = t.innerHTML.slice(0, 8192); } catch (e) {}
  }
});

document.body.addEventListener("htmx:afterSwap", function(evt) {
  var d = evt.detail || {};
  var r = findPendingRecord(true, true);
  if (!r) return;
  r.timing.afterSwap = Date.now();
  if (state.flash && d.target) flashTarget(d.target, r.failed ? "error" : "normal");

  if (d.target && r.domBefore != null) {
    try {
      r.domAfter = d.target.innerHTML.slice(0, 8192);
      if (r.domBefore !== r.domAfter) {
        r.domDiff = diffLines(r.domBefore, r.domAfter);
      }
    } catch (e) {}
  }
});

document.body.addEventListener("htmx:afterSettle", function(evt) {
  var r = findPendingRecord(true, true);
  if (r) r.timing.settle = Date.now();
});

document.body.addEventListener("htmx:oobBeforeSwap", function(evt) {
  var d = evt.detail || {};
  var r = {
    id: "oob-" + Date.now() + "-" + Math.random().toString(36).slice(2),
    path: "OOB",
    method: "OOB",
    target: (d.target && d.target.id) ? "#" + d.target.id : "",
    swap: (d.swapStyle && d.swapStyle) || "innerHTML",
    status: null,
    timing: { config: Date.now() },
    failed: false,
    isOob: true,
    expanded: false,
  };
  state.oobRecords.unshift(r);
  if (state.oobRecords.length > 50) state.oobRecords.pop();
  state.requestCount++;
  updatePill();
});

document.body.addEventListener("htmx:oobAfterSwap", function(evt) {
  var d = evt.detail || {};
  if (state.flash && d.target) flashTarget(d.target, "oob");
});

document.body.addEventListener("htmx:oobErrorNoTarget", function(evt) {
  state.errorCount++;
  addError("OOB Error", "OOB swap had no target");
  toast("OOB Error", "OOB swap had no target", COLORS.error);
});
