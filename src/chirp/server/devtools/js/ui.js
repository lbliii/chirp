// --- ui.js — Styles, DOM, panels, rendering ---

// DRY: standard button style
var BTN_STYLE = "padding:4px 10px;background:#333;border:none;border-radius:4px;color:var(--chirp-text);cursor:pointer;font-size:12px";

function createBtn(text, onClick, style) {
  var btn = document.createElement("button");
  btn.type = "button";
  btn.textContent = text;
  btn.setAttribute("style", style || BTN_STYLE);
  btn.addEventListener("click", function(ev) { ev.stopPropagation(); onClick(ev); });
  return btn;
}

// DRY: highlighted section shorthand
function hlSection(title, content, startOpen) {
  return makeSection(title, '<div class="chirp-dbg-hl">' + content + '</div>', startOpen);
}

// DRY: badge management
function manageBadge(parent, cls, text, show) {
  var badge = parent.querySelector("." + cls);
  if (show) {
    if (!badge) {
      badge = document.createElement("span");
      badge.className = cls;
      parent.appendChild(badge);
    }
    badge.textContent = text;
  } else if (badge) {
    badge.remove();
  }
}

// --- Styles ---
function injectStyles() {
  if (document.getElementById("chirp-debug-styles")) return;
  var style = document.createElement("style");
  style.id = "chirp-debug-styles";
  style.textContent = [
    "#chirp-debug{position:fixed;inset:0;overflow:hidden;pointer-events:none;z-index:99998;font-family:ui-monospace,SF Mono,Menlo,monospace;font-size:14px;line-height:1.5;--chirp-bg:" + COLORS.bg + ";--chirp-text:" + COLORS.text + ";--chirp-success:" + COLORS.success + ";--chirp-warning:" + COLORS.warning + ";--chirp-error:" + COLORS.error + ";--chirp-info:" + COLORS.info + ";--chirp-oob:" + COLORS.oob + ";--chirp-sse:" + COLORS.sse + ";--chirp-vt:" + COLORS.vt + "}",
    ".chirp-dbg-pill{position:fixed;bottom:16px;right:16px;z-index:99998;background:var(--chirp-bg);color:var(--chirp-text);border:1px solid var(--chirp-info);border-radius:20px;padding:6px 12px;cursor:pointer;display:flex;align-items:center;gap:8px;box-shadow:0 4px 12px rgba(0,0,0,.3)}",
    ".chirp-dbg-pill:hover{background:#252530}",
    ".chirp-dbg-pill .chirp-dbg-badge{background:var(--chirp-info);color:var(--chirp-bg);border-radius:10px;padding:2px 6px;font-size:10px}",
    ".chirp-dbg-pill .chirp-dbg-badge.err{background:var(--chirp-error)}",
    ".chirp-dbg-pill .chirp-dbg-badge.sse{background:var(--chirp-sse)}",
    ".chirp-dbg-drawer{position:fixed;bottom:0;left:0;right:0;height:280px;max-height:80vh;z-index:99997;background:var(--chirp-bg);border-top:1px solid #333;display:flex;flex-direction:column;transform:translateY(100%);transition:transform .2s ease}",
    ".chirp-dbg-drawer.open{transform:translateY(0)}",
    ".chirp-dbg-resize{height:4px;cursor:ns-resize;background:#333;flex-shrink:0}",
    ".chirp-dbg-resize:hover{background:var(--chirp-info)}",
    ".chirp-dbg-tabs{display:flex;gap:0;border-bottom:1px solid #333;flex-shrink:0}",
    ".chirp-dbg-tab{padding:8px 16px;cursor:pointer;color:var(--chirp-text);border-bottom:2px solid transparent}",
    ".chirp-dbg-tab:hover{background:#252530}",
    ".chirp-dbg-tab.active{border-bottom-color:var(--chirp-info);color:var(--chirp-info)}",
    ".chirp-dbg-tab .badge{background:var(--chirp-error);color:var(--chirp-bg);border-radius:8px;padding:1px 5px;font-size:10px;margin-left:4px}",
    ".chirp-dbg-tab .badge-sse{background:var(--chirp-sse);color:var(--chirp-bg);border-radius:8px;padding:1px 5px;font-size:10px;margin-left:4px}",
    ".chirp-dbg-help{padding:6px 16px;font-size:11px;color:#7c8396;border-bottom:1px solid #2a2e3a;background:#15161f;flex-shrink:0;line-height:1.4}",
    ".chirp-dbg-help kbd{display:inline-block;padding:1px 5px;border:1px solid #444;border-radius:3px;background:#0d0e14;font-size:10px;color:#a9b1d6}",
    ".chirp-dbg-layout-hint{font-size:11px;color:#7aa2f7;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}",
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
    ".chirp-dbg-waterfall{display:inline-flex;align-items:center;height:10px;min-width:80px;max-width:200px;border-radius:2px;overflow:hidden;background:#1e1f2e;flex-shrink:0}",
    ".chirp-dbg-wf-seg{height:100%;min-width:1px}",
    ".chirp-dbg-sse-conn{padding:10px 12px;border-radius:4px;margin-bottom:6px;background:#1e1f2e;border-left:3px solid var(--chirp-sse)}",
    ".chirp-dbg-sse-conn .url{color:var(--chirp-sse);font-weight:bold}",
    ".chirp-dbg-sse-conn .meta{color:#7c8396;font-size:12px}",
    ".chirp-dbg-sse-evt{padding:6px 12px;margin-bottom:2px;font-size:13px;border-radius:3px}",
    ".chirp-dbg-sse-evt:hover{background:#252530}",
    ".chirp-dbg-sse-evt .evt-type{font-weight:bold;min-width:60px;display:inline-block}",
    ".chirp-dbg-vt-row{padding:8px 12px;border-radius:4px;margin-bottom:4px;display:flex;align-items:center;gap:10px;background:#1e1f2e;border-left:3px solid var(--chirp-vt)}",
    ".chirp-dbg-vt-row .vt-label{color:var(--chirp-vt);font-weight:bold}",
    ".chirp-dbg-section{margin:8px 0}",
    ".chirp-dbg-section-header{cursor:pointer;color:var(--chirp-info);font-weight:bold;font-size:12px;text-transform:uppercase;letter-spacing:.5px;padding:4px 0;user-select:none}",
    ".chirp-dbg-section-header:hover{color:#9bb8ff}",
    ".chirp-dbg-section-header::before{content:'\u25b8 ';font-size:10px}",
    ".chirp-dbg-section-header.open::before{content:'\u25be '}",
    ".chirp-dbg-section-body{display:none;padding:8px 0}",
    ".chirp-dbg-section-body.open{display:block}",
    ".chirp-dbg-hl{background:#0d0e14;border-radius:4px;padding:10px 12px;overflow-x:auto;font-size:12px;line-height:1.6;white-space:pre-wrap;word-break:break-word}",
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
    copyText(full);
  });
  el.addEventListener("click", function(e) { if (!e.target.classList.contains("copy")) el.remove(); });
  box.appendChild(el);
  setTimeout(function() { el.remove(); }, 12000);
}

// --- Waterfall ---
function renderWaterfall(t) {
  if (!t || !t.config) return "";
  var total = (t.settle || t.afterSwap || t.response || t.sent || t.config) - t.config;
  if (total <= 0) return "";
  var segments = [];
  if (t.sent) segments.push({ start: 0, end: t.sent - t.config, color: COLORS.info, label: "prep" });
  if (t.sent && t.response) segments.push({ start: t.sent - t.config, end: t.response - t.config, color: COLORS.success, label: "rtt" });
  if (t.response && t.afterSwap) segments.push({ start: t.response - t.config, end: t.afterSwap - t.config, color: COLORS.warning, label: "swap" });
  if (t.afterSwap && t.settle) segments.push({ start: t.afterSwap - t.config, end: t.settle - t.config, color: "#565f89", label: "settle" });
  if (segments.length === 0) return "";

  var w = 120;
  var bars = segments.map(function(s) {
    var x = (s.start / total) * w;
    var bw = Math.max(1, ((s.end - s.start) / total) * w);
    return '<div class="chirp-dbg-wf-seg" style="width:' + bw + 'px;background:' + s.color + '" title="' + s.label + ' ' + (s.end - s.start) + 'ms"></div>';
  }).join("");
  return '<div class="chirp-dbg-waterfall">' + bars + '</div>';
}

// --- Collapsible section ---
function makeSection(title, contentHTML, startOpen) {
  var sec = document.createElement("div");
  sec.className = "chirp-dbg-section";
  var hdr = document.createElement("div");
  hdr.className = "chirp-dbg-section-header" + (startOpen ? " open" : "");
  hdr.textContent = title;
  var body = document.createElement("div");
  body.className = "chirp-dbg-section-body" + (startOpen ? " open" : "");
  body.innerHTML = contentHTML;
  hdr.addEventListener("click", function() {
    hdr.classList.toggle("open");
    body.classList.toggle("open");
  });
  sec.appendChild(hdr);
  sec.appendChild(body);
  return sec;
}

// --- Panel DOM ---
var panelRoot, drawer, togglePill, activityPanel, errorsPanel, inspectorPanel, ssePanel;
var tabsEl, tabNames;

function refreshActivityPanel() {
  if (activityPanel && state.tab === "activity") renderActivityLog();
}

function refreshSsePanel() {
  if (ssePanel && state.tab === "sse") renderSseLog();
  updatePill();
}

function renderPanel() {
  if (panelRoot) return;
  injectStyles();
  loadState();

  panelRoot = document.createElement("div");
  panelRoot.id = "chirp-debug";
  panelRoot.setAttribute("style", "position:fixed;inset:0;pointer-events:none;z-index:99998;overflow:hidden");

  togglePill = document.createElement("div");
  togglePill.className = "chirp-dbg-pill";
  togglePill.setAttribute(
    "title",
    "Chirp DevTools \u2014 Click to open drawer. Shortcuts: Ctrl+Shift+D toggle drawer, Ctrl+Shift+K inspector, Esc close."
  );
  togglePill.innerHTML = "<span style='letter-spacing:-1px'>\u2301\u2301</span><span class='chirp-dbg-badge'>0</span>";
  if (state.errorCount > 0) {
    var eb = document.createElement("span");
    eb.className = "chirp-dbg-badge err";
    eb.textContent = state.errorCount;
    togglePill.appendChild(eb);
  }
  if (state.sseConnections.length > 0) {
    var sb = document.createElement("span");
    sb.className = "chirp-dbg-badge sse";
    sb.textContent = "SSE " + state.sseConnections.length;
    togglePill.appendChild(sb);
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

  tabsEl = document.createElement("div");
  tabsEl.className = "chirp-dbg-tabs";
  tabNames = ["activity", "sse", "inspector", "errors"];
  tabNames.forEach(function(name) {
    var t = document.createElement("div");
    t.className = "chirp-dbg-tab" + (state.tab === name ? " active" : "");
    t.textContent = name === "sse" ? "SSE" : name.charAt(0).toUpperCase() + name.slice(1);
    if (name === "errors" && state.errors.length > 0) {
      var b = document.createElement("span");
      b.className = "badge";
      b.textContent = state.errors.length;
      t.appendChild(b);
    }
    if (name === "sse" && state.sseConnections.length > 0) {
      var sb2 = document.createElement("span");
      sb2.className = "badge-sse";
      sb2.textContent = state.sseConnections.length;
      t.appendChild(sb2);
    }
    t.addEventListener("click", function() {
      state.tab = name;
      saveState();
      renderTabs();
      renderPanelContent();
    });
    tabsEl.appendChild(t);
  });
  drawer.appendChild(tabsEl);

  var helpBar = document.createElement("div");
  helpBar.className = "chirp-dbg-help";
  helpBar.innerHTML =
    "<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>D</kbd> drawer \u00b7 " +
    "<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>K</kbd> inspector \u00b7 " +
    "<kbd>Esc</kbd> close \u00b7 " +
    "<label style='margin-left:8px;cursor:pointer'><input type='checkbox' id='chirp-dbg-verbose-cb' style='vertical-align:middle'> Verbose console</label> \u00b7 " +
    "<label style='cursor:pointer'><input type='checkbox' id='chirp-dbg-pause-cb' style='vertical-align:middle'> Pause capture</label> \u00b7 " +
    "<label style='cursor:pointer'><input type='checkbox' id='chirp-dbg-redact-cb' style='vertical-align:middle'> Redact curl</label> \u00b7 " +
    "<button type='button' id='chirp-dbg-export-btn' style='padding:2px 8px;font-size:11px;cursor:pointer;background:#333;border:1px solid #555;border-radius:4px;color:inherit'>Export JSON</button>";
  drawer.appendChild(helpBar);

  activityPanel = document.createElement("div");
  activityPanel.className = "chirp-dbg-panel";
  activityPanel.style.display = state.tab === "activity" ? "block" : "none";

  ssePanel = document.createElement("div");
  ssePanel.className = "chirp-dbg-panel";
  ssePanel.style.display = state.tab === "sse" ? "block" : "none";

  inspectorPanel = document.createElement("div");
  inspectorPanel.className = "chirp-dbg-panel";
  inspectorPanel.style.display = state.tab === "inspector" ? "block" : "none";
  inspectorPanel.innerHTML =
    "<p>Hover elements to preview inherited <code>hx-*</code>. Click to pin. " +
    "Use <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>K</kbd> when the drawer is open (avoids browser DevTools on <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>I</kbd>).</p>" +
    "<div class='chirp-dbg-filter' style='flex-direction:column;align-items:flex-start'>" +
    "<label><input type='checkbox' id='chirp-dbg-flash-cb'> Swap flash highlights</label>" +
    "<button id='chirp-dbg-inspector-btn' type='button'>Toggle Inspector</button>" +
    "</div>";

  errorsPanel = document.createElement("div");
  errorsPanel.className = "chirp-dbg-panel";
  errorsPanel.style.display = state.tab === "errors" ? "block" : "none";

  drawer.appendChild(activityPanel);
  drawer.appendChild(ssePanel);
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
  try {
    var verbCb = document.getElementById("chirp-dbg-verbose-cb");
    if (verbCb) {
      verbCb.checked = localStorage.getItem(STORAGE_KEYS.verbose) === "1";
      verbCb.addEventListener("change", function() {
        try { localStorage.setItem(STORAGE_KEYS.verbose, verbCb.checked ? "1" : "0"); } catch (err) {}
      });
    }
    var pauseCb = document.getElementById("chirp-dbg-pause-cb");
    if (pauseCb) {
      pauseCb.checked = state.paused;
      pauseCb.addEventListener("change", function() {
        state.paused = pauseCb.checked;
        saveState();
      });
    }
    var redactCb = document.getElementById("chirp-dbg-redact-cb");
    if (redactCb) {
      redactCb.checked = state.redactCurl;
      redactCb.addEventListener("change", function() {
        state.redactCurl = redactCb.checked;
        saveState();
      });
    }
    var exportBtn = document.getElementById("chirp-dbg-export-btn");
    if (exportBtn) {
      exportBtn.addEventListener("click", function() {
        var payload = JSON.stringify({
          exportedAt: new Date().toISOString(),
          records: state.records,
          errors: state.errors,
          sseConnections: state.sseConnections,
          sseEvents: state.sseEvents,
          vtEvents: state.vtEvents,
        }, null, 2);
        copyText(payload);
        try {
          var blob = new Blob([payload], { type: "application/json" });
          var a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = "chirp-htmx-debug-export.json";
          a.click();
          URL.revokeObjectURL(a.href);
        } catch (err) {}
      });
    }
  } catch (e) {}

  function renderTabs() {
    var ts = tabsEl.querySelectorAll(".chirp-dbg-tab");
    tabNames.forEach(function(name, i) {
      ts[i].className = "chirp-dbg-tab" + (state.tab === name ? " active" : "");
      manageBadge(ts[i], "badge", state.errors.length, name === "errors" && state.errors.length > 0);
      manageBadge(ts[i], "badge-sse", state.sseConnections.length, name === "sse" && state.sseConnections.length > 0);
    });
  }

  renderPanelContent();
  updatePill();
}

function renderPanelContent() {
  activityPanel.style.display = state.tab === "activity" ? "block" : "none";
  ssePanel.style.display = state.tab === "sse" ? "block" : "none";
  inspectorPanel.style.display = state.tab === "inspector" ? "block" : "none";
  errorsPanel.style.display = state.tab === "errors" ? "block" : "none";

  if (state.tab === "activity") renderActivityLog();
  if (state.tab === "sse") renderSseLog();
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
    state.vtEvents = [];
    filterText = "";
    filterErrorsOnly = false;
    renderActivityLog();
    updatePill();
  });

  var all = state.records.concat(state.oobRecords).map(function(r) {
    return { type: "htmx", data: r, ts: (r.timing && r.timing.config) || 0 };
  }).concat(state.vtEvents.map(function(v) {
    return { type: "vt", data: v, ts: v.startedAt || 0 };
  }));
  all.sort(function(a, b) { return b.ts - a.ts; });

  var lower = filterText.toLowerCase();
  var filtered = all.filter(function(item) {
    if (item.type === "vt") return !filterErrorsOnly && (!lower || "view transition".indexOf(lower) >= 0);
    var r = item.data;
    if (filterErrorsOnly) {
      var isErr = r.failed || (r.status != null && r.status >= 400);
      if (!isErr) return false;
    }
    if (!lower) return true;
    var hay = (r.path || "") + (r.method || "") + (r.target || "") + (r.requestId || "");
    if (r.layout) hay += (r.layout.chain || "") + (r.layout.match || "") + (r.layout.mode || "");
    if (r.route) hay += (r.route.kind || "") + (r.route.section || "") + (r.route.meta || "");
    if (r.renderIntent) hay += r.renderIntent;
    return hay.toLowerCase().indexOf(lower) >= 0;
  });

  filtered.forEach(function(item) {
    if (item.type === "vt") {
      var v = item.data;
      var vtRow = document.createElement("div");
      vtRow.className = "chirp-dbg-vt-row";
      var readyMs = v.readyAt ? (v.readyAt - v.startedAt) + "ms ready" : "pending";
      var finMs = v.finishedAt ? (v.finishedAt - v.startedAt) + "ms total" : "";
      vtRow.innerHTML =
        "<span class='vt-label'>[VT]</span>" +
        "<span>View Transition</span>" +
        "<span style='color:#7c8396'>" + readyMs + (finMs ? " \u00b7 " + finMs : "") + "</span>" +
        (v.skipped ? "<span style='color:" + COLORS.error + "'>skipped</span>" : "");
      activityPanel.appendChild(vtRow);
      return;
    }

    var r = item.data;
    var row = document.createElement("div");
    row.className = "chirp-dbg-log-row" + (r.expanded ? " expanded" : "");
    var statusColor = r.status === null ? "#666" : r.status >= 500 ? COLORS.error : r.status >= 400 ? COLORS.warning : r.status >= 300 ? COLORS.info : COLORS.success;
    var t = r.timing || {};
    var rtt = t.sent && t.response ? t.response - t.sent : null;
    var swapMs = t.response && t.afterSwap ? t.afterSwap - t.response : null;
    var settleMs = t.afterSwap && t.settle ? t.settle - t.afterSwap : null;
    var time = "";
    if (rtt != null) {
      time = rtt + "ms";
      if (swapMs != null) time += " \u00b7 swap " + swapMs + "ms";
      if (settleMs != null) time += " \u00b7 settle " + settleMs + "ms";
    } else if (t.config) time = "--";
    var layoutHint = "";
    if (r.layout) {
      if (r.layout.mode) layoutHint = r.layout.mode;
      if (r.layout.chain) {
        var ch = r.layout.chain;
        if (ch.length > 42) ch = ch.slice(0, 40) + "\u2026";
        layoutHint = layoutHint ? layoutHint + " \u00b7 " + ch : ch;
      }
    }
    row.innerHTML =
      "<span class='method'>" + (r.isOob ? "[OOB]" : "[" + r.method + "]") + "</span>" +
      "<span class='path'>" + (r.path || "-") + "</span>" +
      "<span class='status' style='color:" + statusColor + "'>" + (r.status || "-") + "</span>" +
      (r.renderIntent
        ? "<span style='font-size:11px;color:#bb9af7;min-width:56px;flex-shrink:0' title='X-Chirp-Render-Intent'>" +
            String(r.renderIntent).replace(/</g, "&lt;") +
          "</span>"
        : "<span style='min-width:0'></span>") +
      renderWaterfall(t) +
      "<span class='time'>" + time + "</span>" +
      (layoutHint
        ? "<span class='chirp-dbg-layout-hint' title='" + esc(layoutHint) + "'>" + esc(layoutHint) + "</span>"
        : "") +
      "<span class='target'>" + (r.target ? "-> " + r.target + " " + r.swap : "") + "</span>";
    row.addEventListener("click", function() {
      r.expanded = !r.expanded;
      renderActivityLog();
    });
    if (r.expanded) {
      var dc = document.createElement("div");
      dc.style.cssText = "width:100%";

      var coreLines = ["Path: " + r.path, "Method: " + r.method, "Target: " + r.target, "Swap: " + r.swap];
      if (r.requestId) coreLines.push("X-Request-Id: " + r.requestId);
      if (r.elt) coreLines.push("Trigger: " + desc(r.elt));
      var coreDetail = document.createElement("div");
      coreDetail.className = "chirp-dbg-log-detail";
      coreDetail.textContent = coreLines.join("\n");
      dc.appendChild(coreDetail);

      if (r.timing && r.timing.config) {
        var tm = r.timing;
        var tl = [];
        tl.push("config=" + (tm.config || "-") + " sent=" + (tm.sent || "-") +
          " response=" + (tm.response || "-") + " afterSwap=" + (tm.afterSwap || "-") + " settle=" + (tm.settle || "-"));
        if (tm.sent && tm.response) tl.push("RTT (sent\u2192response): " + (tm.response - tm.sent) + "ms");
        if (tm.response && tm.afterSwap) tl.push("Swap (response\u2192afterSwap): " + (tm.afterSwap - tm.response) + "ms");
        if (tm.afterSwap && tm.settle) tl.push("Settle (afterSwap\u2192settle): " + (tm.settle - tm.afterSwap) + "ms");
        dc.appendChild(hlSection("Timing", esc(tl.join("\n")), false));
      }

      if (r.layout) {
        var ll = [];
        ll.push("Chain: " + (r.layout.chain || "(empty)"));
        ll.push("Match: " + (r.layout.match || "(empty)"));
        ll.push("Mode: " + (r.layout.mode || "(empty)"));
        dc.appendChild(hlSection("Layout", esc(ll.join("\n")), false));
      }

      if (r.route) {
        var rl = [];
        rl.push("kind=" + r.route.kind + " section=" + r.route.section);
        if (r.route.meta) rl.push("meta: " + r.route.meta);
        if (r.route.files) rl.push("files: " + r.route.files);
        if (r.route.contextChain) rl.push("context chain: " + r.route.contextChain);
        if (r.route.shellContext) rl.push("shell context: " + r.route.shellContext);
        dc.appendChild(hlSection("Route", esc(rl.join("\n")), false));
      }

      if (r.renderPlan) {
        dc.appendChild(hlSection("Render Plan", esc(formatRenderPlan(r.renderPlan)), false));
      }

      if (r.requestHeaders && typeof r.requestHeaders === "object") {
        var hxReqLines = [];
        var hxReqKeys = ["HX-Request", "HX-Target", "HX-Trigger", "HX-Trigger-Name",
          "HX-Boosted", "HX-History-Restore-Request", "HX-Current-URL", "HX-Prompt"];
        for (var ki = 0; ki < hxReqKeys.length; ki++) {
          var hk = hxReqKeys[ki];
          if (r.requestHeaders[hk]) hxReqLines.push(hk + ": " + r.requestHeaders[hk]);
        }
        if (hxReqLines.length) {
          dc.appendChild(hlSection("htmx Request Headers", hlHeaders(hxReqLines.join("\n")), false));
        }
      }

      if (r.hxTriggerEvents && r.hxTriggerEvents.length) {
        var tl = r.hxTriggerEvents.map(function(te) {
          var line = te.name;
          if (te.phase !== "HX-Trigger") line += "  (" + te.phase + ")";
          if (te.data && te.data !== true) line += "  " + JSON.stringify(te.data);
          return line;
        }).join("\n");
        dc.appendChild(hlSection("Triggered Events (" + r.hxTriggerEvents.length + ")", esc(tl), false));
      }

      if (r.hxPairs && r.hxPairs.length) {
        var ht = r.hxPairs.map(function(p) { return p[0] + ": " + p[1]; }).join("\n");
        dc.appendChild(hlSection("HX / X-Chirp Response Headers", hlHeaders(ht), false));
      }

      if (r.bodyPreview) {
        var bodyHtml;
        var ct = r.contentType || "";
        if (ct.indexOf("json") >= 0) {
          bodyHtml = hlJSON(esc(r.bodyPreview));
        } else {
          bodyHtml = esc(r.bodyPreview);
        }
        var label = r.status >= 400 ? "Response Body (error)" : "Response Body";
        dc.appendChild(hlSection(label, bodyHtml, r.status >= 400));
      }

      if (r.domDiff && r.domDiff.length > 0) {
        dc.appendChild(hlSection("DOM Diff (swap)", hlDiff(r.domDiff), false));
      }

      dc.appendChild(hlSection("Replay (curl)", esc(buildCurl(r)), false));

      if (r.elt) {
        dc.appendChild(hlSection("Effective hx-*", esc(formatConfig(getEffectiveConfig(r.elt))), false));
      }

      var btnRow = document.createElement("div");
      btnRow.setAttribute("style", "display:flex;gap:8px;flex-wrap:wrap;margin-top:8px");
      btnRow.appendChild(createBtn("Copy all", function() { copyText(dc.textContent || ""); }));
      btnRow.appendChild(createBtn("Copy curl", function() { copyText(buildCurl(r)); }));

      if (r.bodyPreview) {
        btnRow.appendChild(createBtn("\u2728 Rosettes highlight", function() {
          var lang = "html";
          if ((r.contentType || "").indexOf("json") >= 0) lang = "json";
          var encoded = btoa(unescape(encodeURIComponent(r.bodyPreview)));
          fetch(HIGHLIGHT_PATH + "?code=" + encodeURIComponent(encoded) + "&lang=" + lang)
            .then(function(res) { return res.json(); })
            .then(function(data) {
              if (data && data.html) {
                var existing = dc.querySelector("[data-rosettes-body]");
                if (existing) existing.remove();
                var hlDiv = document.createElement("div");
                hlDiv.setAttribute("data-rosettes-body", "1");
                hlDiv.className = "chirp-dbg-hl";
                hlDiv.innerHTML = data.html;
                dc.insertBefore(hlDiv, btnRow);
              }
            })
            .catch(function() {});
        }, "padding:4px 10px;background:#1e3a5f;border:none;border-radius:4px;color:var(--chirp-info);cursor:pointer;font-size:12px"));
      }

      dc.appendChild(btnRow);
      row.appendChild(dc);
    }
    activityPanel.appendChild(row);
  });
}

// --- SSE Panel ---
function renderSseLog() {
  ssePanel.innerHTML = "";
  if (state.sseConnections.length === 0 && state.sseEvents.length === 0) {
    ssePanel.innerHTML = "<p style='color:#7c8396'>No SSE connections detected yet. EventSource connections will appear here automatically.</p>";
    return;
  }

  state.sseConnections.forEach(function(conn) {
    var card = document.createElement("div");
    card.className = "chirp-dbg-sse-conn";
    var stateLabel = conn.readyState === 0 ? "CONNECTING" : conn.readyState === 1 ? "OPEN" : "CLOSED";
    var stateColor = conn.readyState === 1 ? COLORS.success : conn.readyState === 0 ? COLORS.warning : "#7c8396";
    card.innerHTML =
      "<div class='url'>" + esc(conn.url) + "</div>" +
      "<div class='meta'>" +
      "<span style='color:" + stateColor + "'>" + stateLabel + "</span> \u00b7 " +
      conn.eventCount + " events \u00b7 " +
      conn.errorCount + " errors" +
      (conn.lastEventAt ? " \u00b7 last: " + new Date(conn.lastEventAt).toLocaleTimeString() : "") +
      "</div>";
    ssePanel.appendChild(card);
  });

  var evtHeader = document.createElement("div");
  evtHeader.style.cssText = "color:#7c8396;font-size:12px;margin:12px 0 6px;text-transform:uppercase;letter-spacing:.5px";
  evtHeader.textContent = "Recent Events (" + state.sseEvents.length + ")";
  ssePanel.appendChild(evtHeader);

  state.sseEvents.slice(0, 50).forEach(function(evt) {
    var evtRow = document.createElement("div");
    evtRow.className = "chirp-dbg-sse-evt";
    var typeColor = evt.type === "error" ? COLORS.error : evt.type === "open" ? COLORS.success : evt.type === "close" ? "#7c8396" : COLORS.sse;
    var timeStr = new Date(evt.ts).toLocaleTimeString();
    evtRow.innerHTML =
      "<span class='evt-type' style='color:" + typeColor + "'>" + esc(evt.type) + "</span>" +
      "<span style='color:#7c8396;font-size:12px'>" + timeStr + "</span> " +
      "<span style='color:#565f89;font-size:12px'>" + esc(evt.url).slice(0, 40) + "</span>" +
      (evt.data ? "<div style='color:" + COLORS.text + ";font-size:12px;margin-top:2px;white-space:pre-wrap'>" + esc(evt.data).slice(0, 120) + "</div>" : "");
    ssePanel.appendChild(evtRow);
  });
}

function renderErrorHistory() {
  errorsPanel.innerHTML = "";
  state.errors.forEach(function(e) {
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
      copyText(full);
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

  var sseBadge = togglePill.querySelector(".chirp-dbg-badge.sse");
  if (state.sseConnections.length > 0) {
    if (!sseBadge) {
      sseBadge = document.createElement("span");
      sseBadge.className = "chirp-dbg-badge sse";
      togglePill.appendChild(sseBadge);
    }
    sseBadge.textContent = "SSE " + state.sseConnections.length;
  } else if (sseBadge) sseBadge.remove();
}
