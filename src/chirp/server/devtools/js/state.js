// --- state.js — Tokens, constants, state object, persistence ---

var COLORS = {
  bg: "#1a1b26",
  text: "#a9b1d6",
  success: "#9ece6a",
  warning: "#e0af68",
  error: "#f7768e",
  info: "#7aa2f7",
  oob: "#bb9af7",
  sse: "#2ac3de",
  vt: "#ff9e64",
};
var BUFFER_SIZE = 200;
var STORAGE_KEYS = {
  open: "chirp-debug-open",
  height: "chirp-debug-height",
  tab: "chirp-debug-tab",
  flash: "chirp-debug-flash",
  inspector: "chirp-debug-inspector",
  verbose: "chirp-debug-verbose",
  pause: "chirp-debug-pause",
  redactCurl: "chirp-debug-redact-curl",
  reloadPlans: "chirp-debug-reload-plans",
};
var HIGHLIGHT_PATH = "/__chirp/debug/highlight";
var DEBUG_TRACES_PATH = "/__chirp/debug/traces.json";

var state = {
  open: false,
  height: 280,
  tab: "activity",
  flash: true,
  inspector: false,
  paused: false,
  redactCurl: false,
  requestCount: 0,
  errorCount: 0,
  records: [],
  errors: [],
  oobRecords: [],
  historyEvents: [],
  pinnedScroll: false,
  sseConnections: [],
  sseEvents: [],
  transitionTraces: [],
  nativeTraceKeys: {},
  vtEvents: [],
  htmxCompatibility: null,
  templateReloadPlans: [],
};

function saveTemplateReloadPlans() {
  try {
    sessionStorage.setItem(STORAGE_KEYS.reloadPlans, JSON.stringify(state.templateReloadPlans));
  } catch (e) {}
}

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
    var p = localStorage.getItem(STORAGE_KEYS.pause);
    if (p !== null) state.paused = p === "true";
    var rc = localStorage.getItem(STORAGE_KEYS.redactCurl);
    if (rc !== null) state.redactCurl = rc === "true";
    var plans = sessionStorage.getItem(STORAGE_KEYS.reloadPlans);
    if (plans) {
      var parsedPlans = JSON.parse(plans);
      if (Array.isArray(parsedPlans)) {
        state.templateReloadPlans = parsedPlans.filter(function(plan) {
          return plan && typeof plan === "object" && plan.schemaVersion === 1 &&
            typeof plan.revision === "number" &&
            ["patch", "diagnose", "reload"].indexOf(plan.outcome) >= 0 &&
            typeof plan.reason === "string" &&
            Array.isArray(plan.changedBlocks) &&
            Array.isArray(plan.addedBlocks) &&
            Array.isArray(plan.removedBlocks);
        }).slice(0, 100);
      }
    }
  } catch (e) {}
}

function saveState() {
  try {
    localStorage.setItem(STORAGE_KEYS.open, String(state.open));
    localStorage.setItem(STORAGE_KEYS.height, String(state.height));
    localStorage.setItem(STORAGE_KEYS.tab, state.tab);
    localStorage.setItem(STORAGE_KEYS.flash, String(state.flash));
    localStorage.setItem(STORAGE_KEYS.inspector, String(state.inspector));
    localStorage.setItem(STORAGE_KEYS.pause, String(state.paused));
    localStorage.setItem(STORAGE_KEYS.redactCurl, String(state.redactCurl));
  } catch (e) {}
}

loadState();
