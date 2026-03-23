// --- helpers.js — Pure utility functions ---

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function copyText(s) {
  navigator.clipboard.writeText(s).catch(function() {});
}

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
  for (var ai = 0; ai < attrs.length; ai++) {
    var attrName = attrs[ai];
    var attrShort = attrName.replace("hx-", "");
    var found = null;
    var node = elt;
    while (node && node !== document.body) {
      if (found === null && node.hasAttribute && node.hasAttribute(attrName)) {
        found = node.getAttribute(attrName);
      }
      if (found !== null && node !== elt) {
        var disinherit = (node.getAttribute && node.getAttribute("hx-disinherit")) || "";
        if (disinherit && (disinherit === "*" || new RegExp("\\b" + attrShort + "\\b").test(disinherit))) {
          found = null;
          break;
        }
      }
      node = node.parentElement;
    }
    result[attrName] = found !== null ? found : "(default)";
  }
  return result;
}

function formatConfig(cfg) {
  var lines = [];
  for (var k in cfg) lines.push(k + ": " + cfg[k]);
  return lines.join("\n");
}

function shellQuote(s) {
  if (s == null) return "''";
  return "'" + String(s).replace(/'/g, "'\\''") + "'";
}

function parseResponseHeaders(xhr) {
  var raw = xhr.getAllResponseHeaders && xhr.getAllResponseHeaders();
  if (!raw) return {};
  var out = {};
  raw.trim().split(/[\r\n]+/).forEach(function(line) {
    var idx = line.indexOf(":");
    if (idx === -1) return;
    var name = line.slice(0, idx).trim().toLowerCase();
    var val = line.slice(idx + 1).trim();
    out[name] = val;
  });
  return out;
}

function filterHxAndChirpHeaders(rh) {
  var list = [];
  for (var k in rh) {
    if (!Object.prototype.hasOwnProperty.call(rh, k)) continue;
    if (k.indexOf("hx-") === 0 || k.indexOf("x-chirp-") === 0) {
      list.push([k, rh[k]]);
    }
  }
  list.sort(function(a, b) { return a[0].localeCompare(b[0]); });
  return list;
}

function buildCurl(r) {
  var path = r.path || "";
  var url = window.location.origin + path;
  if (state.redactCurl && url.indexOf("?") >= 0) {
    url = url.split("?")[0];
  }
  var m = (r.method || "GET").toUpperCase();
  var parts = ["curl", "-sS", "-i"];
  if (m !== "GET") {
    parts.push("-X", shellQuote(m));
  }
  if (r.requestHeaders && typeof r.requestHeaders === "object") {
    for (var hk in r.requestHeaders) {
      if (!Object.prototype.hasOwnProperty.call(r.requestHeaders, hk)) continue;
      if (state.redactCurl && /^(cookie|authorization)$/i.test(hk)) continue;
      parts.push("-H", shellQuote(hk + ": " + r.requestHeaders[hk]));
    }
  }
  parts.push(shellQuote(url));
  return parts.join(" ");
}

function firePlugin(name, arg) {
  var ch = window.ChirpHtmxDebug;
  if (!ch || typeof ch[name] !== "function") return;
  try { ch[name](arg); } catch (e) {}
}
