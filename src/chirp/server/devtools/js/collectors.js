// --- collectors.js — HTMX/SSE/VT event collectors ---

// DRY: shared SSE event push
function pushSseEvent(connId, type, url, data) {
  state.sseEvents.unshift({ connId: connId, type: type, url: url, ts: Date.now(), data: data });
  if (state.sseEvents.length > BUFFER_SIZE) state.sseEvents.pop();
  refreshSsePanel();
}

// --- SSE Monitor (native Chirp EventStream traces) ---
function findSseConnection(id) {
  for (var i = 0; i < state.sseConnections.length; i++) {
    if (state.sseConnections[i].id === id) return state.sseConnections[i];
  }
  return null;
}

function ensureNativeSseConnection(rec) {
  var id = "sse-" + rec.request_id;
  var conn = findSseConnection(id);
  if (conn) return conn;
  conn = {
    id: id,
    url: rec.path,
    openedAt: null,
    closedAt: null,
    readyState: 0,
    eventCount: 0,
    errorCount: 0,
    lastEventAt: null,
    native: true,
    owner: rec.owner || "app",
  };
  state.sseConnections.unshift(conn);
  if (state.sseConnections.length > 20) state.sseConnections.pop();
  return conn;
}

function ingestNativeSseTrace(rec) {
  if (!rec || rec.channel !== "sse") return;
  var key = rec.channel + ":" + rec.request_id + ":" + rec.phase + ":" + rec.ts_ms;
  if (state.nativeTraceKeys[key]) return;
  state.nativeTraceKeys[key] = true;
  var conn = ensureNativeSseConnection(rec);
  if (rec.phase === "start") {
    conn.openedAt = rec.ts_ms;
    conn.readyState = 1;
  } else if (rec.phase === "closed" || rec.phase === "disconnect" || rec.phase === "cancelled") {
    conn.closedAt = rec.ts_ms;
    conn.readyState = 2;
  } else if (rec.phase === "event" || rec.phase === "retry" || rec.phase === "heartbeat") {
    conn.eventCount++;
    conn.readyState = 1;
    conn.lastEventAt = rec.ts_ms;
  } else if (rec.phase === "render_error" || rec.phase === "generator_error" || rec.phase === "send_failed") {
    conn.errorCount++;
    conn.lastEventAt = rec.ts_ms;
  }
  var data = rec.data ? JSON.stringify(rec.data).slice(0, 200) : "";
  state.sseEvents.unshift({
    connId: conn.id,
    type: rec.phase,
    url: rec.path,
    ts: rec.ts_ms || Date.now(),
    data: data,
  });
  if (state.sseEvents.length > BUFFER_SIZE) state.sseEvents.pop();
  refreshSsePanel();
}

function refreshNativeSseTraces(includeInternal) {
  if (!window.fetch) return;
  var url = DEBUG_TRACES_PATH + (includeInternal ? "?internal=1" : "");
  fetch(url, { credentials: "same-origin", cache: "no-store" })
    .then(function(res) { return res.ok ? res.json() : null; })
    .then(function(payload) {
      if (!payload || !payload.records) return;
      payload.records.forEach(ingestNativeSseTrace);
    })
    .catch(function() {});
}

setInterval(function() {
  if (state.open || state.tab === "sse") refreshNativeSseTraces(false);
}, 2000);

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
var recordByXhr = typeof WeakMap !== "undefined" ? new WeakMap() : null;

function findPendingRecord(hasSent, hasResponse) {
  for (var i = 0; i < state.records.length; i++) {
    var r = state.records[i];
    if (!!r.timing.sent !== hasSent) continue;
    if (!!r.timing.response !== hasResponse) continue;
    return r;
  }
  return null;
}

function rememberRecordForDetail(detail, record) {
  if (!detail || !detail.xhr || !recordByXhr || !record) return;
  try { recordByXhr.set(detail.xhr, record); } catch (e) {}
}

function getRecordForDetail(detail, hasSent, hasResponse) {
  if (detail && detail.xhr && recordByXhr) {
    try {
      var existing = recordByXhr.get(detail.xhr);
      if (existing) return existing;
    } catch (e) {}
  }
  var r = findPendingRecord(hasSent, hasResponse);
  if (!r && hasSent && !hasResponse) r = findPendingRecord(false, false);
  if (!r && hasSent && hasResponse) r = findPendingRecord(true, false) || findPendingRecord(false, false);
  rememberRecordForDetail(detail, r);
  return r;
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
    hxTriggerEvents: null,
    renderIntent: "",
    bodyPreview: "",
    contentType: "",
    renderPlan: null,
    returnTrace: null,
    effectiveConfigDetails: null,
    select: "",
    selectMatched: null,
    targetExistsBefore: null,
    targetBefore: "",
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
  r.effectiveConfigDetails = getEffectiveConfigDetails(d.elt);
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
  var d = evt.detail || {};
  var r = getRecordForDetail(d, false, false);
  if (r) r.timing.sent = Date.now();
});

document.body.addEventListener("htmx:afterRequest", function(evt) {
  var d = evt.detail || {};
  var r = getRecordForDetail(d, true, false);
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
    var rtHeader = xhr.getResponseHeader && xhr.getResponseHeader("X-Chirp-Return-Trace");
    if (rtHeader) {
      r.returnTrace = decodeRenderPlan(rtHeader);
    }

    // Extract HX-Trigger events for devtools display
    var triggerHeaders = ["HX-Trigger", "HX-Trigger-After-Settle", "HX-Trigger-After-Swap"];
    var triggerEvents = [];
    for (var ti = 0; ti < triggerHeaders.length; ti++) {
      var tv = xhr.getResponseHeader && xhr.getResponseHeader(triggerHeaders[ti]);
      if (tv) {
        try {
          var parsed = JSON.parse(tv);
          if (typeof parsed === "object" && parsed !== null) {
            for (var ek in parsed) {
              if (Object.prototype.hasOwnProperty.call(parsed, ek)) {
                triggerEvents.push({ name: ek, phase: triggerHeaders[ti], data: parsed[ek] });
              }
            }
          }
        } catch (e) {
          // Plain string event name
          triggerEvents.push({ name: tv, phase: triggerHeaders[ti], data: null });
        }
      }
    }
    if (triggerEvents.length) r.hxTriggerEvents = triggerEvents;

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
  var r = getRecordForDetail(d, true, true);
  if (!r) return;
  var t = d.target;
  r.target = (t && t.id) ? "#" + t.id : (t && t.className && String(t.className).trim()) ? "." + String(t.className).split(/\s+/)[0] : (t ? "this" : "");
  r.swap = (d.swapStyle && d.swapStyle) || "innerHTML";
  r.timing.beforeSwap = Date.now();
  r.targetExistsBefore = !!t;
  r.targetBefore = t ? desc(t) : "";

  var cfg = r.effectiveConfigDetails || (r.elt ? getEffectiveConfigDetails(r.elt) : {});
  var select = cfg["hx-select"] && cfg["hx-select"].value;
  var xhr = d.xhr;
  if (select && select !== "(default)" && xhr && xhr.responseText) {
    r.select = select;
    r.selectMatched = responseContainsSelector(xhr.responseText, select);
  }

  if (t) {
    try { r.domBefore = t.innerHTML.slice(0, 8192); } catch (e) {}
  }
});

document.body.addEventListener("htmx:afterSwap", function(evt) {
  var d = evt.detail || {};
  var r = getRecordForDetail(d, true, true);
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
  var d = evt.detail || {};
  var r = getRecordForDetail(d, true, true);
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
