// --- collectors.js — HTMX/SSE/VT event collectors ---

// DRY: shared SSE event push
function pushSseEvent(connId, type, url, data) {
  state.sseEvents.unshift({ connId: connId, type: type, url: url, ts: Date.now(), data: data });
  if (state.sseEvents.length > BUFFER_SIZE) state.sseEvents.pop();
  refreshSsePanel();
}

// --- Template reload planner records ---
function reloadPlanText(value, limit) {
  if (value == null) return null;
  return String(value).slice(0, limit);
}

function reloadPlanList(value) {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 50).map(function(item) { return String(item).slice(0, 160); });
}

function normalizeTemplateReloadPlan(value) {
  if (!value || typeof value !== "object" || value.schema_version !== 1) return null;
  var revision = Number(value.revision);
  if (!isFinite(revision) || revision < 1 || Math.floor(revision) !== revision) return null;
  if (["patch", "diagnose", "reload"].indexOf(value.outcome) < 0) return null;
  var reason = reloadPlanText(value.reason, 160);
  if (!reason) return null;
  return {
    schemaVersion: 1,
    revision: revision,
    outcome: value.outcome,
    reason: reason,
    templateName: reloadPlanText(value.template_name, 240),
    changedBlocks: reloadPlanList(value.changed_blocks),
    addedBlocks: reloadPlanList(value.added_blocks),
    removedBlocks: reloadPlanList(value.removed_blocks),
    targetId: reloadPlanText(value.target_id, 160),
    errorType: reloadPlanText(value.error_type, 160),
    errorLine: typeof value.error_line === "number" ? value.error_line : null,
    requiresResponseValidation: value.requires_response_validation === true,
    receivedAt: Date.now(),
  };
}

function ingestTemplateReloadPlan(value) {
  var plan = normalizeTemplateReloadPlan(value);
  if (!plan) return;
  state.templateReloadPlans.unshift(plan);
  if (state.templateReloadPlans.length > 100) state.templateReloadPlans.pop();
  saveTemplateReloadPlans();
  refreshReloadPanel();
}

window.addEventListener("chirp:reload-plan", function(evt) {
  ingestTemplateReloadPlan(evt.detail);
});

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

function ingestNativeHttpTrace(rec) {
  if (!rec || rec.channel !== "http" || !rec.data || !rec.data.observation_id) return;
  var key = rec.channel + ":" + rec.request_id + ":" + rec.data.observation_id;
  if (state.nativeTraceKeys[key]) return;
  state.nativeTraceKeys[key] = true;
  state.transitionTraces.unshift({
    requestId: rec.request_id,
    ts: rec.ts_ms,
    routePath: rec.path,
    observationId: rec.data.observation_id,
    routeId: rec.data.route_id,
    requestMode: rec.data.request_mode,
    modeTags: rec.data.mode_tags || [],
    compiledTransitionIds: rec.data.compiled_transition_ids || [],
    transitionDescriptions: rec.data.transition_descriptions || [],
  });
  if (state.transitionTraces.length > BUFFER_SIZE) state.transitionTraces.pop();
}

function buildTransitionCoverage(expectedModes) {
  var modes = {};
  var transitions = {};
  var observations = {};
  state.transitionTraces.forEach(function(trace) {
    observations[trace.observationId] = true;
    (trace.modeTags || []).forEach(function(mode) { modes[mode] = true; });
    (trace.compiledTransitionIds || []).forEach(function(id) { transitions[id] = true; });
  });
  var expected = expectedModes || [];
  var untested = expected.filter(function(mode) { return !modes[mode]; });
  return {
    observationIds: Object.keys(observations).sort(),
    observedModes: Object.keys(modes).sort(),
    untestedModes: untested.slice().sort(),
    compiledTransitionIds: Object.keys(transitions).sort(),
  };
}

function refreshNativeSseTraces(includeInternal) {
  if (!window.fetch) return;
  var url = DEBUG_TRACES_PATH + (includeInternal ? "?internal=1" : "");
  fetch(url, { credentials: "same-origin", cache: "no-store" })
    .then(function(res) { return res.ok ? res.json() : null; })
    .then(function(payload) {
      if (!payload || !payload.records) return;
      payload.records.forEach(function(rec) {
        ingestNativeSseTrace(rec);
        ingestNativeHttpTrace(rec);
      });
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
var recordByContext = typeof WeakMap !== "undefined" ? new WeakMap() : null;
var recordByRequest = typeof WeakMap !== "undefined" ? new WeakMap() : null;

function htmxContext(detail) {
  return detail && detail.ctx ? detail.ctx : (detail || {});
}

function htmxSource(detail) {
  detail = detail || {};
  var ctx = htmxContext(detail);
  return ctx.sourceElement || detail.elt ||
    (detail.requestConfig && detail.requestConfig.elt) || null;
}

function htmxRequest(detail) {
  detail = detail || {};
  var ctx = htmxContext(detail);
  return ctx.request || {};
}

function htmxResponse(detail) {
  detail = detail || {};
  var ctx = htmxContext(detail);
  return (ctx.response && (ctx.response.raw || ctx.response)) || detail.xhr || null;
}

function htmxAction(detail, source) {
  detail = detail || {};
  var request = htmxRequest(detail);
  var requestConfig = detail.requestConfig || {};
  if (request.action || requestConfig.path || detail.path) {
    return String(request.action || requestConfig.path || detail.path);
  }
  if (detail.pathInfo && detail.pathInfo.requestPath) {
    return String(detail.pathInfo.requestPath);
  }
  if (!source || !source.getAttribute) return "";
  var attrs = ["hx-get", "hx-post", "hx-put", "hx-patch", "hx-delete", "hx-action"];
  for (var i = 0; i < attrs.length; i++) {
    var value = source.getAttribute(attrs[i]);
    if (value) return value;
  }
  return "";
}

function mappedRecordForDetail(detail) {
  if (!detail) return null;
  var ctx = htmxContext(detail);
  var req = htmxRequest(detail);
  try {
    if (detail.xhr && recordByXhr && recordByXhr.has(detail.xhr)) {
      return recordByXhr.get(detail.xhr);
    }
    if (req && typeof req === "object" && recordByRequest && recordByRequest.has(req)) {
      return recordByRequest.get(req);
    }
    if (ctx && typeof ctx === "object" && recordByContext && recordByContext.has(ctx)) {
      return recordByContext.get(ctx);
    }
  } catch (e) {}
  return null;
}

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
  if (!detail || !record) return;
  var ctx = htmxContext(detail);
  var req = htmxRequest(detail);
  try {
    if (detail.xhr && recordByXhr) recordByXhr.set(detail.xhr, record);
    if (req && typeof req === "object" && recordByRequest) recordByRequest.set(req, record);
    if (ctx && typeof ctx === "object" && recordByContext) recordByContext.set(ctx, record);
  } catch (e) {}
}

function getRecordForDetail(detail, hasSent, hasResponse) {
  var existing = mappedRecordForDetail(detail);
  if (existing) return existing;
  var r = findPendingRecord(hasSent, hasResponse);
  if (!r && hasSent && !hasResponse) r = findPendingRecord(false, false);
  if (!r && hasSent && hasResponse) r = findPendingRecord(true, false) || findPendingRecord(false, false);
  rememberRecordForDetail(detail, r);
  return r;
}

function onHtmxEvents(names, handler) {
  for (var i = 0; i < names.length; i++) {
    document.addEventListener(names[i], handler);
  }
}

function onHtmxEventPair(names, handler) {
  var seen = typeof WeakSet !== "undefined" ? new WeakSet() : null;
  onHtmxEvents(names, function(evt) {
    var detail = evt.detail || {};
    var token = htmxContext(detail);
    if (seen && token && typeof token === "object") {
      if (seen.has(token)) return;
      seen.add(token);
    }
    handler(evt);
  });
}

function createRecord() {
  var r = {
    id: "req-" + Date.now() + "-" + Math.random().toString(36).slice(2),
    path: "",
    method: "GET",
    source: "",
    methodSemantics: "safe",
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
    signalEmits: null,
    effectiveConfigDetails: null,
    synchronization: null,
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

function collectConfigRequest(evt) {
  if (state.paused) return;
  var d = evt.detail || {};
  var existing = mappedRecordForDetail(d);
  if (existing && existing.timing.config) return;
  var ctx = htmxContext(d);
  var request = htmxRequest(d);
  var elt = htmxSource(d) || evt.target;
  var r = createRecord();
  r.path = htmxAction(d, elt);
  r.method = String(request.method || d.verb || (d.parameters && d.parameters["_method"]) || (elt && (
    elt.getAttribute("hx-post") ? "POST" :
    elt.getAttribute("hx-put") ? "PUT" :
    elt.getAttribute("hx-patch") ? "PATCH" :
    elt.getAttribute("hx-delete") ? "DELETE" : "GET"
  )));
  r.method = r.method.toUpperCase();
  r.methodSemantics = classifyMethod(r.method);
  r.elt = elt;
  r.source = elt ? desc(elt) : "";
  var target = ctx.target || d.target;
  r.target = target ? desc(target) : "";
  r.effectiveConfigDetails = getEffectiveConfigDetails(elt);
  if (elt && elt.getAttribute) {
    var syncValue = elt.getAttribute("hx-sync");
    if (syncValue) {
      var separator = syncValue.lastIndexOf(":");
      r.synchronization = {
        owner: separator >= 0 ? syncValue.slice(0, separator).trim() : "this",
        strategy: separator >= 0 ? syncValue.slice(separator + 1).trim() : syncValue.trim(),
      };
    }
  }
  r.timing.config = Date.now();
  try {
    r.requestHeaders = copyRequestHeaders(request.headers || d.headers);
  } catch (e) {
    r.requestHeaders = {};
  }
  rememberRecordForDetail(d, r);
  firePlugin("onRequest", r);
}
onHtmxEvents(["htmx:configRequest", "htmx:config:request"], collectConfigRequest);

function collectBeforeRequest(evt) {
  var d = evt.detail || {};
  var r = getRecordForDetail(d, false, false);
  if (!r || r.timing.sent) return;
  r.timing.sent = Date.now();
  rememberRecordForDetail(d, r);
}
onHtmxEvents(["htmx:beforeRequest", "htmx:before:request"], collectBeforeRequest);

function collectAfterRequest(evt) {
  var d = evt.detail || {};
  var r = getRecordForDetail(d, true, false);
  if (!r || r.timing.response) return;
  var ctx = htmxContext(d);
  var response = htmxResponse(d);
  if (response || ctx.response) {
    r.status = Number((ctx.response && ctx.response.status) || response.status || 0);
    r.timing.response = Date.now();
    rememberRecordForDetail(d, r);
    if (r.status >= 400) {
      r.failed = true;
      state.errorCount++;
    }
    var routeKind = readResponseHeader(response, "X-Chirp-Route-Kind");
    if (routeKind) {
      r.route = {
        kind: routeKind,
        meta: readResponseHeader(response, "X-Chirp-Route-Meta") || "",
        files: readResponseHeader(response, "X-Chirp-Route-Files") || "",
        section: readResponseHeader(response, "X-Chirp-Route-Section") || "",
        contextChain: readResponseHeader(response, "X-Chirp-Context-Chain") || "",
        shellContext: readResponseHeader(response, "X-Chirp-Shell-Context") || "",
      };
    }
    var layoutChain = readResponseHeader(response, "X-Chirp-Layout-Chain");
    var layoutMatch = readResponseHeader(response, "X-Chirp-Layout-Match");
    var layoutMode = readResponseHeader(response, "X-Chirp-Layout-Mode");
    if (layoutChain || layoutMatch || layoutMode) {
      r.layout = {
        chain: layoutChain || "",
        match: layoutMatch || "",
        mode: layoutMode || "",
      };
    }
    var reqId = readResponseHeader(response, "X-Request-Id");
    if (reqId) r.requestId = reqId;
    var rh = parseResponseHeaders(response);
    r.responseHeaders = rh;
    r.contentType = rh["content-type"] || "";
    r.renderIntent = rh["x-chirp-render-intent"] || "";
    r.hxPairs = filterHxAndChirpHeaders(rh);

    var rpHeader = readResponseHeader(response, "X-Chirp-Render-Plan");
    if (rpHeader) {
      r.renderPlan = decodeRenderPlan(rpHeader);
    }
    var rtHeader = readResponseHeader(response, "X-Chirp-Return-Trace");
    if (rtHeader) {
      r.returnTrace = decodeRenderPlan(rtHeader);
    }
    var seHeader = readResponseHeader(response, "X-Chirp-Signal-Emits");
    if (seHeader) {
      r.signalEmits = decodeRenderPlan(seHeader);
    }

    // Extract HX-Trigger events for devtools display
    var triggerHeaders = ["HX-Trigger", "HX-Trigger-After-Settle", "HX-Trigger-After-Swap"];
    var triggerEvents = [];
    var triggerTier = collectHtmxCompatibility().configuredTier;
    for (var ti = 0; ti < triggerHeaders.length; ti++) {
      var tv = readResponseHeader(response, triggerHeaders[ti]);
      if (tv) {
        try {
          var parsed = JSON.parse(tv);
          if (typeof parsed === "object" && parsed !== null) {
            for (var ek in parsed) {
              if (Object.prototype.hasOwnProperty.call(parsed, ek)) {
                triggerEvents.push({
                  name: ek,
                  phase: triggerHeaders[ti],
                  data: parsed[ek],
                  support: triggerTier === "4-preview" && triggerHeaders[ti] !== "HX-Trigger" ?
                    "unsupported" : "wire",
                });
              }
            }
          }
        } catch (e) {
          // Plain string event name
          triggerEvents.push({
            name: tv,
            phase: triggerHeaders[ti],
            data: null,
            support: triggerTier === "4-preview" && triggerHeaders[ti] !== "HX-Trigger" ?
              "unsupported" : "wire",
          });
        }
      }
    }
    if (triggerEvents.length) r.hxTriggerEvents = triggerEvents;

    var responseText = ctx.text != null ? ctx.text : (d.xhr && d.xhr.responseText);
    if (responseText) {
      var txt = String(responseText);
      r.bodyPreview =
        txt.length > 4096
          ? txt.slice(0, 4096) + "\n\u2026 (truncated, " + txt.length + " bytes total)"
          : txt;
    }
    firePlugin("onResponse", r);
  }
}
onHtmxEvents(["htmx:afterRequest", "htmx:after:request"], collectAfterRequest);

function collectBeforeSwap(evt) {
  var d = evt.detail || {};
  var r = getRecordForDetail(d, true, true);
  if (!r || r.timing.beforeSwap) return;
  var ctx = htmxContext(d);
  var t = ctx.target || d.target;
  r.target = (t && t.id) ? "#" + t.id : (t && t.className && String(t.className).trim()) ? "." + String(t.className).split(/\s+/)[0] : (t ? "this" : "");
  var configuredSwap = r.effectiveConfigDetails && r.effectiveConfigDetails["hx-swap"];
  r.swap = (typeof ctx.swap === "string" && ctx.swap) || d.swapStyle ||
    (configuredSwap && configuredSwap.value !== "(default)" ? configuredSwap.value : "innerHTML");
  r.timing.beforeSwap = Date.now();
  r.targetExistsBefore = !!t;
  r.targetBefore = t ? desc(t) : "";

  var cfg = r.effectiveConfigDetails || (r.elt ? getEffectiveConfigDetails(r.elt) : {});
  var select = cfg["hx-select"] && cfg["hx-select"].value;
  var responseText = ctx.text != null ? ctx.text : (d.xhr && d.xhr.responseText);
  if (select && select !== "(default)" && responseText) {
    r.select = select;
    r.selectMatched = responseContainsSelector(responseText, select);
  }

  if (t) {
    try { r.domBefore = t.innerHTML.slice(0, 8192); } catch (e) {}
  }
  if (Array.isArray(d.tasks)) {
    for (var taskIndex = 1; taskIndex < d.tasks.length; taskIndex++) {
      var task = d.tasks[taskIndex] || {};
      recordOobSwap(task.target || task.elt, task.swap || task.swapStyle, r);
    }
    for (var markedIndex = 0; markedIndex < d.tasks.length; markedIndex++) {
      var marked = d.tasks[markedIndex] || {};
      if (marked.oob || marked.isOob) {
        recordOobSwap(marked.target || marked.elt, marked.swap || marked.swapStyle, r);
      }
    }
  }
}
onHtmxEvents(["htmx:beforeSwap", "htmx:before:swap"], collectBeforeSwap);

function collectAfterSwap(evt) {
  var d = evt.detail || {};
  var r = getRecordForDetail(d, true, true);
  if (!r || r.timing.afterSwap) return;
  var ctx = htmxContext(d);
  var target = ctx.target || d.target;
  r.timing.afterSwap = Date.now();
  if (state.flash && target) flashTarget(target, r.failed ? "error" : "normal");

  if (target && r.domBefore != null) {
    try {
      r.domAfter = target.innerHTML.slice(0, 8192);
      if (r.domBefore !== r.domAfter) {
        r.domDiff = diffLines(r.domBefore, r.domAfter);
      }
    } catch (e) {}
  }
}
onHtmxEvents(["htmx:afterSwap", "htmx:after:swap"], collectAfterSwap);

function collectAfterSettle(evt) {
  var d = evt.detail || {};
  var r = getRecordForDetail(d, true, true);
  if (r && !r.timing.settle) r.timing.settle = Date.now();
}
onHtmxEvents(["htmx:afterSettle", "htmx:after:settle"], collectAfterSettle);

function collectHistoryEvent(kind, names) {
  onHtmxEventPair(names, function(evt) {
    var detail = evt.detail || {};
    var record = {
      kind: kind,
      path: htmxAction(detail, htmxSource(detail)) || String(detail.path || location.pathname),
      ts: Date.now(),
    };
    state.historyEvents.unshift(record);
    if (state.historyEvents.length > BUFFER_SIZE) state.historyEvents.pop();
  });
}

collectHistoryEvent("update", ["htmx:beforeHistorySave", "htmx:before:history:update"]);
collectHistoryEvent("push", ["htmx:pushedIntoHistory", "htmx:after:history:push"]);
collectHistoryEvent("replace", ["htmx:replacedInHistory", "htmx:after:history:replace"]);
collectHistoryEvent("restore", [
  "htmx:historyCacheMiss",
  "htmx:historyRestore",
  "htmx:before:history:restore",
]);

function recordOobSwap(target, swapStyle, parentRecord) {
  var targetName = (target && target.id) ? "#" + target.id : (target ? desc(target) : "");
  var key = targetName + ":" + (swapStyle || "innerHTML");
  if (parentRecord) {
    parentRecord._oobKeys = parentRecord._oobKeys || {};
    if (parentRecord._oobKeys[key]) return;
    parentRecord._oobKeys[key] = true;
  }
  var r = {
    id: "oob-" + Date.now() + "-" + Math.random().toString(36).slice(2),
    path: "OOB",
    method: "OOB",
    target: targetName,
    swap: swapStyle || "innerHTML",
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
}

document.body.addEventListener("htmx:oobBeforeSwap", function(evt) {
  var d = evt.detail || {};
  var swap = d.swapStyle || (d.elt && d.elt.getAttribute && d.elt.getAttribute("hx-swap-oob"));
  recordOobSwap(d.target, swap, getRecordForDetail(d, true, true));
});

document.body.addEventListener("htmx:oobAfterSwap", function(evt) {
  var d = evt.detail || {};
  if (state.flash && d.target) flashTarget(d.target, "oob");
});

document.body.addEventListener("htmx:oobErrorNoTarget", function(evt) {
  state.errorCount++;
  toast("OOB Error", "OOB swap had no target", COLORS.error);
});
