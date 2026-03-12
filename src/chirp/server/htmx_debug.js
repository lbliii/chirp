(function() {
  if (window.__chirpHtmxDebugBooted) return;
  window.__chirpHtmxDebugBooted = true;

  // --- Tokens ---
  var COLORS = {
    bg: "#1a1b26",
    text: "#a9b1d6",
    success: "#9ece6a",
    warning: "#e0af68",
    error: "#f7768e",
    info: "#7aa2f7",
    oob: "#bb9af7",
  };
  var BUFFER_SIZE = 200;
  var STORAGE_KEYS = {
    open: "chirp-debug-open",
    height: "chirp-debug-height",
    tab: "chirp-debug-tab",
    flash: "chirp-debug-flash",
    inspector: "chirp-debug-inspector",
  };

  // --- Helpers ---
  function desc(el) {
    if (!el || !el.tagName) return "(unknown element)";
    var tag = "<" + el.tagName.toLowerCase() + ">";
    var id = el.id ? "#" + el.id : "";
    return tag + id;
  }

  function getEffectiveConfig(elt) {
    if (!elt || !elt.getAttribute) return {};
    var attrs = [
      "hx-get", "hx-post", "hx-put", "hx-patch", "hx-delete",
      "hx-target", "hx-swap", "hx-select", "hx-trigger", "hx-push-url",
    ];
    var result = {};
    var node = elt;
    while (node && node !== document.body) {
      var disinherit = (node.getAttribute && node.getAttribute("hx-disinherit")) || "";
      for (var i = 0; i < attrs.length; i++) {
        var a = attrs[i];
        if (disinherit && new RegExp(a.replace("hx-", "")).test(disinherit)) continue;
        var v = node.getAttribute && node.getAttribute(a);
        if (v !== null && result[a] === undefined) result[a] = v;
      }
      node = node.parentElement;
    }
    for (var j = 0; j < attrs.length; j++) {
      if (result[attrs[j]] === undefined) result[attrs[j]] = "(default)";
    }
    return result;
  }

  function formatConfig(cfg) {
    var lines = [];
    for (var k in cfg) lines.push(k + ": " + cfg[k]);
    return lines.join("\n");
  }

  // --- State ---
  var state = {
    open: false,
    height: 280,
    tab: "activity",
    flash: true,
    inspector: false,
    requestCount: 0,
    errorCount: 0,
    records: [],
    errors: [],
    oobRecords: [],
    pinnedScroll: false,
  };

  function loadState() {
    try {
      var o = localStorage.getItem(STORAGE_KEYS.open);
      if (o !== null) state.open = o === "true";
      var h = localStorage.getItem(STORAGE_KEYS.height);
      if (h !== null) state.height = parseInt(h, 10) || 280;
      var t = localStorage.getItem(STORAGE_KEYS.tab);
      if (t) state.tab = t;
      var f = localStorage.getItem(STORAGE_KEYS.flash);
      if (f !== null) state.flash = f === "true";
      var i = localStorage.getItem(STORAGE_KEYS.inspector);
      if (i !== null) state.inspector = i === "true";
    } catch (e) {}
  }

  function saveState() {
    try {
      localStorage.setItem(STORAGE_KEYS.open, String(state.open));
      localStorage.setItem(STORAGE_KEYS.height, String(state.height));
      localStorage.setItem(STORAGE_KEYS.tab, state.tab);
      localStorage.setItem(STORAGE_KEYS.flash, String(state.flash));
      localStorage.setItem(STORAGE_KEYS.inspector, String(state.inspector));
    } catch (e) {}
  }

  // --- Event Collector ---
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
    };
    state.records.unshift(r);
    if (state.records.length > BUFFER_SIZE) state.records.pop();
    state.requestCount++;
    return r;
  }

  document.body.addEventListener("htmx:configRequest", function(evt) {
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
  });

  document.body.addEventListener("htmx:afterSwap", function(evt) {
    var d = evt.detail || {};
    var r = findPendingRecord(true, true);
    if (!r) return;
    r.timing.afterSwap = Date.now();
    if (state.flash && d.target) flashTarget(d.target, r.failed ? "error" : "normal");
  });

  document.body.addEventListener("htmx:afterSettle", function(evt) {
    var r = findPendingRecord(true, true);
    if (!r) return;
    r.timing.settle = Date.now();
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
  });

  document.body.addEventListener("htmx:oobAfterSwap", function(evt) {
    var d = evt.detail || {};
    if (state.flash && d.target) flashTarget(d.target, "oob");
  });

  document.body.addEventListener("htmx:oobErrorNoTarget", function(evt) {
    var d = evt.detail || {};
    state.errorCount++;
    var msg = "OOB swap had no target";
    addError("OOB Error", msg);
    toast("OOB Error", msg, COLORS.error);
  });

  // --- Styles ---
  function injectStyles() {
    if (document.getElementById("chirp-debug-styles")) return;
    var style = document.createElement("style");
    style.id = "chirp-debug-styles";
    style.textContent = [
      "#chirp-debug{position:fixed;inset:0;overflow:hidden;pointer-events:none;z-index:99998;font-family:ui-monospace,SF Mono,Menlo,monospace;font-size:14px;line-height:1.5;--chirp-bg:" + COLORS.bg + ";--chirp-text:" + COLORS.text + ";--chirp-success:" + COLORS.success + ";--chirp-warning:" + COLORS.warning + ";--chirp-error:" + COLORS.error + ";--chirp-info:" + COLORS.info + ";--chirp-oob:" + COLORS.oob + "}",
      ".chirp-dbg-pill{position:fixed;bottom:16px;right:16px;z-index:99998;background:var(--chirp-bg);color:var(--chirp-text);border:1px solid var(--chirp-info);border-radius:20px;padding:6px 12px;cursor:pointer;display:flex;align-items:center;gap:8px;box-shadow:0 4px 12px rgba(0,0,0,.3)}",
      ".chirp-dbg-pill:hover{background:#252530}",
      ".chirp-dbg-pill .chirp-dbg-badge{background:var(--chirp-info);color:var(--chirp-bg);border-radius:10px;padding:2px 6px;font-size:10px}",
      ".chirp-dbg-pill .chirp-dbg-badge.err{background:var(--chirp-error)}",
      ".chirp-dbg-drawer{position:fixed;bottom:0;left:0;right:0;height:280px;max-height:80vh;z-index:99997;background:var(--chirp-bg);border-top:1px solid #333;display:flex;flex-direction:column;transform:translateY(100%);transition:transform .2s ease}",
      ".chirp-dbg-drawer.open{transform:translateY(0)}",
      ".chirp-dbg-resize{height:4px;cursor:ns-resize;background:#333;flex-shrink:0}",
      ".chirp-dbg-resize:hover{background:var(--chirp-info)}",
      ".chirp-dbg-tabs{display:flex;gap:0;border-bottom:1px solid #333;flex-shrink:0}",
      ".chirp-dbg-tab{padding:8px 16px;cursor:pointer;color:var(--chirp-text);border-bottom:2px solid transparent}",
      ".chirp-dbg-tab:hover{background:#252530}",
      ".chirp-dbg-tab.active{border-bottom-color:var(--chirp-info);color:var(--chirp-info)}",
      ".chirp-dbg-tab .badge{background:var(--chirp-error);color:var(--chirp-bg);border-radius:8px;padding:1px 5px;font-size:10px;margin-left:4px}",
      ".chirp-dbg-panel{flex:1;overflow:auto;padding:16px}",
      ".chirp-dbg-log-row{padding:10px 12px;border-radius:4px;cursor:pointer;margin-bottom:4px;display:flex;align-items:flex-start;gap:10px;flex-wrap:wrap}",
      ".chirp-dbg-log-row:hover{background:#252530}",
      ".chirp-dbg-log-row.expanded{background:#252530}",
      ".chirp-dbg-log-row .method{font-weight:bold;min-width:40px}",
      ".chirp-dbg-log-row .path{flex:1;overflow:hidden;text-overflow:ellipsis}",
      ".chirp-dbg-log-row .status{min-width:36px}",
      ".chirp-dbg-log-row .time{min-width:40px;color:#7c8396}",
      ".chirp-dbg-log-row .target{color:#9aa2c9;font-size:13px}",
      ".chirp-dbg-log-detail{padding:12px 14px;margin:6px 0;background:#0d0e14;border-radius:4px;font-size:13px;line-height:1.5;white-space:pre-wrap;word-break:break-word}",
      ".chirp-dbg-filter{display:flex;gap:8px;margin-bottom:8px;flex-wrap:wrap}",
      ".chirp-dbg-filter input{flex:1;min-width:120px;padding:6px 8px;background:#0d0e14;border:1px solid #333;border-radius:4px;color:var(--chirp-text)}",
      ".chirp-dbg-filter button{padding:6px 12px;background:#333;border:none;border-radius:4px;color:var(--chirp-text);cursor:pointer}",
      ".chirp-dbg-filter button:hover{background:#444}",
      ".chirp-dbg-toast{pointer-events:auto;background:var(--chirp-bg);color:var(--chirp-text);border:1px solid;border-left:4px solid;border-radius:6px;padding:12px 16px;max-width:440px;font-size:14px;line-height:1.5;display:flex;align-items:flex-start;gap:8px}",
      ".chirp-dbg-toast .body{flex:1;white-space:pre-wrap}",
      ".chirp-dbg-toast .copy{cursor:pointer;opacity:.7}",
      ".chirp-dbg-toast .copy:hover{opacity:1}",
      ".chirp-dbg-inspector-overlay{position:fixed;inset:0;z-index:99996;pointer-events:none}",
      ".chirp-dbg-inspector-overlay.active{pointer-events:auto}",
      ".chirp-dbg-highlight{outline:2px solid var(--chirp-info);outline-offset:2px;pointer-events:none}",
      ".chirp-dbg-tooltip{position:fixed;background:var(--chirp-bg);border:1px solid var(--chirp-info);border-radius:6px;padding:12px;max-width:420px;font-size:13px;line-height:1.5;white-space:pre-wrap;z-index:99999;pointer-events:auto;box-shadow:0 4px 12px rgba(0,0,0,.4)}",
      ".chirp-dbg-err-row{display:flex;flex-direction:column;gap:4px;padding:12px;border-radius:4px;cursor:pointer;margin-bottom:6px;background:#1e1f2e;border-left:4px solid var(--chirp-error)}",
      ".chirp-dbg-err-row:hover{background:#252530}",
      ".chirp-dbg-err-row .chirp-dbg-err-title{font-weight:bold;color:var(--chirp-error);font-size:14px}",
      ".chirp-dbg-err-row .chirp-dbg-err-body{color:var(--chirp-text);white-space:pre-wrap;word-break:break-word;font-size:14px;line-height:1.5}",
      "@keyframes chirp-dbg-flash{0%{outline-color:var(--chirp-info);outline-width:3px}100%{outline-color:transparent;outline-width:0}}",
      "@keyframes chirp-dbg-flash-oob{0%{outline-color:var(--chirp-oob);outline-width:3px}100%{outline-color:transparent;outline-width:0}}",
      "@keyframes chirp-dbg-flash-err{0%{outline-color:var(--chirp-error);outline-width:3px}100%{outline-color:transparent;outline-width:0}}",
    ].join("\n");
    document.head.appendChild(style);
  }

  // --- Swap Flash ---
  function flashTarget(el, kind) {
    if (!el || !el.style) return;
    var anim = kind === "oob" ? "chirp-dbg-flash-oob" : kind === "error" ? "chirp-dbg-flash-err" : "chirp-dbg-flash";
    el.style.outline = "2px solid transparent";
    el.style.outlineOffset = "2px";
    el.style.animation = anim + " 0.6s ease-out forwards";
    setTimeout(function() {
      el.style.animation = "";
      el.style.outline = "";
      el.style.outlineOffset = "";
    }, 600);
  }

  // --- Toast ---
  function getToastBox() {
    var existing = document.getElementById("chirp-htmx-debug-toasts");
    if (existing) return existing;
    var box = document.createElement("div");
    box.id = "chirp-htmx-debug-toasts";
    box.setAttribute("style", "position:fixed;bottom:16px;right:16px;z-index:99999;display:flex;flex-direction:column-reverse;gap:8px;max-height:60vh;overflow-y:auto;pointer-events:none;");
    document.body.appendChild(box);
    return box;
  }

  function addError(title, body, configStr) {
    state.errors.unshift({ title: title, body: body, config: configStr || "", ts: Date.now() });
    if (state.errors.length > 100) state.errors.pop();
  }

  function toast(title, body, color, configStr) {
    addError(title, body, configStr);
    var box = getToastBox();
    var el = document.createElement("div");
    el.className = "chirp-dbg-toast";
    el.style.borderColor = color;
    el.style.borderLeftColor = color;
    var full = title + "\n\n" + body + (configStr ? "\n\n" + configStr : "");
    el.innerHTML =
      "<div style='color:" + color + ";font-weight:bold;margin-bottom:4px'>" + title + "</div>" +
      "<div class='body'>" + body.replace(/</g, "&lt;").replace(/>/g, "&gt;") + "</div>" +
      "<span class='copy' title='Copy'>\u2398</span>";
    el.querySelector(".copy").addEventListener("click", function(e) {
      e.stopPropagation();
      navigator.clipboard.writeText(full).catch(function() {});
    });
    el.addEventListener("click", function(e) { if (!e.target.classList.contains("copy")) el.remove(); });
    box.appendChild(el);
    setTimeout(function() { el.remove(); }, 12000);
  }

  // --- Panel DOM ---
  var panelRoot, drawer, togglePill, activityPanel, errorsPanel, inspectorPanel;

  function renderPanel() {
    if (panelRoot) return;
    injectStyles();
    loadState();

    panelRoot = document.createElement("div");
    panelRoot.id = "chirp-debug";
    panelRoot.setAttribute("style", "position:fixed;inset:0;pointer-events:none;z-index:99998;overflow:hidden");

    togglePill = document.createElement("div");
    togglePill.className = "chirp-dbg-pill";
    togglePill.innerHTML = "<span>HTMX</span><span class='chirp-dbg-badge'>0</span>";
    if (state.errorCount > 0) {
      var eb = document.createElement("span");
      eb.className = "chirp-dbg-badge err";
      eb.textContent = state.errorCount;
      togglePill.appendChild(eb);
    }
    togglePill.addEventListener("click", toggleDrawer);
    togglePill.style.pointerEvents = "auto";
    panelRoot.appendChild(togglePill);

    drawer = document.createElement("div");
    drawer.className = "chirp-dbg-drawer" + (state.open ? " open" : "");
    drawer.style.height = state.height + "px";
    drawer.style.pointerEvents = "auto";

    var resize = document.createElement("div");
    resize.className = "chirp-dbg-resize";
    var resizing = false;
    var startY = 0, startH = 0;
    resize.addEventListener("mousedown", function(e) {
      resizing = true;
      startY = e.clientY;
      startH = state.height;
      e.preventDefault();
    });
    document.addEventListener("mousemove", function(e) {
      if (!resizing) return;
      var dy = startY - e.clientY;
      state.height = Math.min(600, Math.max(120, startH + dy));
      drawer.style.height = state.height + "px";
      saveState();
    });
    document.addEventListener("mouseup", function() { resizing = false; });
    drawer.appendChild(resize);

    var tabs = document.createElement("div");
    tabs.className = "chirp-dbg-tabs";
    var tabNames = ["activity", "inspector", "errors"];
    tabNames.forEach(function(name) {
      var t = document.createElement("div");
      t.className = "chirp-dbg-tab" + (state.tab === name ? " active" : "");
      t.textContent = name.charAt(0).toUpperCase() + name.slice(1);
      if (name === "errors" && state.errors.length > 0) {
        var b = document.createElement("span");
        b.className = "badge";
        b.textContent = state.errors.length;
        t.appendChild(b);
      }
      t.addEventListener("click", function() {
        state.tab = name;
        saveState();
        renderTabs();
        renderPanelContent();
      });
      tabs.appendChild(t);
    });
    drawer.appendChild(tabs);

    activityPanel = document.createElement("div");
    activityPanel.className = "chirp-dbg-panel";
    activityPanel.style.display = state.tab === "activity" ? "block" : "none";

    inspectorPanel = document.createElement("div");
    inspectorPanel.className = "chirp-dbg-panel";
    inspectorPanel.style.display = state.tab === "inspector" ? "block" : "none";
    inspectorPanel.innerHTML =
      "<p>Click 'Toggle Inspector' or press Ctrl+Shift+I to inspect element htmx attributes.</p>" +
      "<div class='chirp-dbg-filter' style='flex-direction:column;align-items:flex-start'>" +
      "<label><input type='checkbox' id='chirp-dbg-flash-cb'> Swap flash highlights</label>" +
      "<button id='chirp-dbg-inspector-btn'>Toggle Inspector</button>" +
      "</div>";

    errorsPanel = document.createElement("div");
    errorsPanel.className = "chirp-dbg-panel";
    errorsPanel.style.display = state.tab === "errors" ? "block" : "none";

    drawer.appendChild(activityPanel);
    drawer.appendChild(inspectorPanel);
    drawer.appendChild(errorsPanel);

    panelRoot.appendChild(drawer);
    document.body.appendChild(panelRoot);

    document.getElementById("chirp-dbg-inspector-btn").addEventListener("click", toggleInspector);
    var flashCb = document.getElementById("chirp-dbg-flash-cb");
    if (flashCb) {
      flashCb.checked = state.flash;
      flashCb.addEventListener("change", function() {
        state.flash = flashCb.checked;
        saveState();
      });
    }

    function renderTabs() {
      var ts = tabs.querySelectorAll(".chirp-dbg-tab");
      tabNames.forEach(function(name, i) {
        ts[i].className = "chirp-dbg-tab" + (state.tab === name ? " active" : "");
        var badge = ts[i].querySelector(".badge");
        if (name === "errors" && state.errors.length > 0) {
          if (!badge) {
            badge = document.createElement("span");
            badge.className = "badge";
            ts[i].appendChild(badge);
          }
          badge.textContent = state.errors.length;
        } else if (badge) badge.remove();
      });
    }

    renderPanelContent();
    updatePill();
  }

  function renderPanelContent() {
    activityPanel.style.display = state.tab === "activity" ? "block" : "none";
    inspectorPanel.style.display = state.tab === "inspector" ? "block" : "none";
    errorsPanel.style.display = state.tab === "errors" ? "block" : "none";

    if (state.tab === "activity") renderActivityLog();
    if (state.tab === "errors") renderErrorHistory();
  }

  var filterText = "";
  var filterErrorsOnly = false;

  function renderActivityLog() {
    activityPanel.innerHTML = "";
    var filter = document.createElement("div");
    filter.className = "chirp-dbg-filter";
    filter.innerHTML =
      "<input type='text' placeholder='Filter...' id='chirp-dbg-filter-input'>" +
      "<label><input type='checkbox' id='chirp-dbg-err-only'> Errors only</label>" +
      "<button id='chirp-dbg-clear'>Clear</button>";
    activityPanel.appendChild(filter);

    var inp = document.getElementById("chirp-dbg-filter-input");
    var errCb = document.getElementById("chirp-dbg-err-only");
    inp.value = filterText;
    errCb.checked = filterErrorsOnly;
    inp.addEventListener("input", function() { filterText = inp.value; renderActivityLog(); });
    errCb.addEventListener("change", function() { filterErrorsOnly = errCb.checked; renderActivityLog(); });
    document.getElementById("chirp-dbg-clear").addEventListener("click", function() {
      state.records = [];
      state.oobRecords = [];
      filterText = "";
      filterErrorsOnly = false;
      renderActivityLog();
      updatePill();
    });

    var all = state.records.concat(state.oobRecords);
    all.sort(function(a, b) {
      var ta = (a.timing && a.timing.config) || 0;
      var tb = (b.timing && b.timing.config) || 0;
      return tb - ta;
    });

    var lower = filterText.toLowerCase();
    var filtered = all.filter(function(r) {
      if (filterErrorsOnly && !r.failed && r.status !== 500) return false;
      if (lower && (r.path + r.method + (r.target || "")).toLowerCase().indexOf(lower) < 0) return false;
      return true;
    });

    filtered.forEach(function(r) {
      var row = document.createElement("div");
      row.className = "chirp-dbg-log-row" + (r.expanded ? " expanded" : "");
      var statusColor = r.status === null ? "#666" : r.status >= 500 ? COLORS.error : r.status >= 400 ? COLORS.warning : r.status >= 300 ? COLORS.info : COLORS.success;
      var time = "";
      if (r.timing && r.timing.sent && r.timing.response) time = (r.timing.response - r.timing.sent) + "ms";
      else if (r.timing && r.timing.config) time = "--";
      row.innerHTML =
        "<span class='method'>" + (r.isOob ? "[OOB]" : "[" + r.method + "]") + "</span>" +
        "<span class='path'>" + (r.path || "-") + "</span>" +
        "<span class='status' style='color:" + statusColor + "'>" + (r.status || "-") + "</span>" +
        "<span class='time'>" + time + "</span>" +
        "<span class='target'>" + (r.target ? "-> " + r.target + " " + r.swap : "") + "</span>";
      row.addEventListener("click", function() {
        r.expanded = !r.expanded;
        renderActivityLog();
      });
      if (r.expanded) {
        var detail = document.createElement("div");
        detail.className = "chirp-dbg-log-detail";
        var parts = ["Path: " + r.path, "Method: " + r.method, "Target: " + r.target, "Swap: " + r.swap];
        if (r.elt) parts.push("Trigger: " + desc(r.elt));
        if (r.timing) {
          parts.push("Timing: config=" + (r.timing.config || "-") + " sent=" + (r.timing.sent || "-") + " response=" + (r.timing.response || "-") + " swap=" + (r.timing.afterSwap || "-") + " settle=" + (r.timing.settle || "-"));
        }
        if (r.route) {
          parts.push("Route: kind=" + r.route.kind + " section=" + r.route.section);
          if (r.route.meta) parts.push("RouteMeta: " + r.route.meta);
          if (r.route.files) parts.push("Files: " + r.route.files);
          if (r.route.contextChain) parts.push("Context chain: " + r.route.contextChain);
          if (r.route.shellContext) parts.push("Shell context: " + r.route.shellContext);
        }
        if (r.elt) {
          var cfg = getEffectiveConfig(r.elt);
          parts.push("Effective hx-*:\n" + formatConfig(cfg));
        }
        detail.textContent = parts.join("\n");
        row.appendChild(detail);
      }
      activityPanel.appendChild(row);
    });
  }

  function renderErrorHistory() {
    errorsPanel.innerHTML = "";
    state.errors.forEach(function(e, i) {
      var row = document.createElement("div");
      row.className = "chirp-dbg-err-row";
      var full = e.title + "\n\n" + e.body + (e.config ? "\n\n" + e.config : "");
      var bodyEscaped = (e.body || "").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      row.innerHTML =
        "<div style='display:flex;align-items:flex-start;justify-content:space-between;gap:8px'>" +
        "<span class='chirp-dbg-err-title'>" + (e.title || "Error") + "</span>" +
        "<span class='copy' title='Copy' style='cursor:pointer;opacity:.8;flex-shrink:0'>\u2398</span>" +
        "</div>" +
        "<div class='chirp-dbg-err-body'>" + bodyEscaped + "</div>";
      row.querySelector(".copy").addEventListener("click", function(ev) {
        ev.stopPropagation();
        navigator.clipboard.writeText(full).catch(function() {});
      });
      if (e.config) {
        var cfgDiv = document.createElement("div");
        cfgDiv.className = "chirp-dbg-log-detail";
        cfgDiv.style.display = "none";
        cfgDiv.textContent = "Effective hx-* attributes:\n" + e.config;
        row.appendChild(cfgDiv);
        row.addEventListener("click", function(ev) {
          if (ev.target.classList.contains("copy")) return;
          cfgDiv.style.display = cfgDiv.style.display === "none" ? "block" : "none";
        });
      }
      errorsPanel.appendChild(row);
    });
  }

  function toggleDrawer() {
    state.open = !state.open;
    drawer.classList.toggle("open", state.open);
    saveState();
    updatePill();
  }

  function toggleInspector() {
    state.inspector = !state.inspector;
    saveState();
    if (state.inspector) startInspector();
    else stopInspector();
  }

  function updatePill() {
    if (!togglePill) return;
    var badges = togglePill.querySelectorAll(".chirp-dbg-badge");
    if (badges[0]) badges[0].textContent = state.requestCount;
    var errBadge = togglePill.querySelector(".chirp-dbg-badge.err");
    if (state.errorCount > 0) {
      if (!errBadge) {
        errBadge = document.createElement("span");
        errBadge.className = "chirp-dbg-badge err";
        togglePill.appendChild(errBadge);
      }
      errBadge.textContent = state.errorCount;
    } else if (errBadge) errBadge.remove();
  }

  // --- Element Inspector ---
  var overlayEl, tooltipEl, highlightEl, pinnedEl;

  function startInspector() {
    if (overlayEl) return;
    overlayEl = document.createElement("div");
    overlayEl.className = "chirp-dbg-inspector-overlay active";
    overlayEl.style.pointerEvents = "auto";
    highlightEl = document.createElement("div");
    highlightEl.className = "chirp-dbg-highlight";
    highlightEl.style.pointerEvents = "none";
    tooltipEl = document.createElement("div");
    tooltipEl.className = "chirp-dbg-tooltip";
    tooltipEl.style.display = "none";

    overlayEl.addEventListener("mousemove", function(e) {
      if (pinnedEl) return;
      var el = document.elementFromPoint(e.clientX, e.clientY);
      if (!el || el === overlayEl || overlayEl.contains(el)) return;
      var rect = el.getBoundingClientRect();
      highlightEl.style.cssText = "position:fixed;left:" + rect.left + "px;top:" + rect.top + "px;width:" + rect.width + "px;height:" + rect.height + "px;";
      highlightEl.style.display = "block";
      if (!highlightEl.parentNode) overlayEl.appendChild(highlightEl);

      var cfg = getEffectiveConfig(el);
      var hasHx = Object.keys(cfg).some(function(k) { return cfg[k] !== "(default)"; });
      if (!hasHx) {
        tooltipEl.style.display = "none";
        return;
      }
      var lines = [desc(el)];
      for (var k in cfg) lines.push(k + ": " + cfg[k] + (cfg[k] === "(default)" ? "" : " (direct)"));
      tooltipEl.textContent = lines.join("\n");
      tooltipEl.style.display = "block";
      tooltipEl.style.left = (e.clientX + 15) + "px";
      tooltipEl.style.top = (e.clientY + 15) + "px";
      if (!tooltipEl.parentNode) overlayEl.appendChild(tooltipEl);
    });

    overlayEl.addEventListener("click", function(e) {
      var el = document.elementFromPoint(e.clientX, e.clientY);
      if (el === overlayEl || overlayEl.contains(el)) return;
      if (pinnedEl === el) {
        pinnedEl = null;
        tooltipEl.style.display = "none";
        return;
      }
      pinnedEl = el;
      var rect = el.getBoundingClientRect();
      highlightEl.style.cssText = "position:fixed;left:" + rect.left + "px;top:" + rect.top + "px;width:" + rect.width + "px;height:" + rect.height + "px;";
      var cfg = getEffectiveConfig(el);
      var lines = [desc(el)];
      for (var k in cfg) lines.push(k + ": " + cfg[k]);
      tooltipEl.textContent = lines.join("\n");
      tooltipEl.style.left = (rect.right + 10) + "px";
      tooltipEl.style.top = rect.top + "px";
      tooltipEl.style.display = "block";
    });

    document.body.appendChild(overlayEl);
  }

  function stopInspector() {
    if (overlayEl && overlayEl.parentNode) overlayEl.parentNode.removeChild(overlayEl);
    overlayEl = null;
    tooltipEl = null;
    highlightEl = null;
    pinnedEl = null;
    state.inspector = false;
    saveState();
  }

  // --- Error event handlers (toasts + error history) ---
  document.body.addEventListener("htmx:targetError", function(evt) {
    var d = evt.detail || {};
    var target = d.target || "(unknown selector)";
    var trigger = desc(d.elt || evt.target);
    var hint =
      "Common cause: target is in a different fragment than the form. Co-locate the target with the mutating element (e.g. put the result div inside the same HTMX-loaded content).";
    var msg = target + "\nTriggered by " + trigger + "\n\n" + hint;
    var cfg = d.elt ? formatConfig(getEffectiveConfig(d.elt)) : "";
    addError("Target Not Found", msg, cfg);
    toast("Target Not Found", msg, COLORS.error, cfg);
  });

  document.body.addEventListener("htmx:responseError", function(evt) {
    var d = evt.detail || {};
    var xhr = d.xhr || {};
    var status = xhr.status || "?";
    var path = (d.pathInfo && d.pathInfo.requestPath) || "";
    var cfg = d.elt ? formatConfig(getEffectiveConfig(d.elt)) : "";
    addError("Response Error", status + " " + path, cfg);
    toast("Response Error", String(status) + " " + path, COLORS.error, cfg);
  });

  document.body.addEventListener("htmx:sendError", function(evt) {
    var d = evt.detail || {};
    var path = (d.pathInfo && d.pathInfo.requestPath) || "";
    var cfg = d.elt ? formatConfig(getEffectiveConfig(d.elt)) : "";
    addError("Network Error", path + "\nIs the server running?", cfg);
    toast("Network Error", path + "\nIs the server running?", COLORS.error, cfg);
  });

  document.body.addEventListener("htmx:swapError", function(evt) {
    var d = evt.detail || {};
    var cfg = d.elt ? formatConfig(getEffectiveConfig(d.elt)) : "";
    addError("Swap Error", String(d.error || "(unknown)"), cfg);
    toast("Swap Error", String(d.error || "(unknown)"), COLORS.warning, cfg);
  });

  document.body.addEventListener("htmx:timeout", function(evt) {
    var d = evt.detail || {};
    var path = (d.pathInfo && d.pathInfo.requestPath) || "";
    addError("Timeout", path);
    toast("Timeout", path, COLORS.warning);
  });

  document.body.addEventListener("htmx:onLoadError", function(evt) {
    var d = evt.detail || {};
    addError("Load Handler Error", String(d.error || "(unknown)"));
    toast("Load Handler Error", String(d.error || "(unknown)"), COLORS.warning);
  });

  document.body.addEventListener("htmx:beforeSwap", function(evt) {
    var d = evt.detail || {};
    var xhr = d.xhr;
    var elt = d.elt;
    if (!xhr || !xhr.responseText || !elt) return;
    var sel = (elt.getAttribute && elt.getAttribute("hx-select")) ||
      (elt.closest && elt.closest("[hx-select]") && elt.closest("[hx-select]").getAttribute("hx-select"));
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
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === "D") {
      e.preventDefault();
      renderPanel();
      toggleDrawer();
    }
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === "I") {
      if (state.open) {
        e.preventDefault();
        renderPanel();
        toggleInspector();
      }
    }
  });

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

  console.log("chirp htmx debug overlay active");
})();
