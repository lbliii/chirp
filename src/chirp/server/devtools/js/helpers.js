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

function disinherits(disinherit, attrName, attrShort) {
  if (!disinherit) return false;
  var normalized = String(disinherit).trim();
  if (normalized === "*") return true;
  return new RegExp("(^|\\s)" + attrName + "(\\s|$)").test(normalized) ||
    new RegExp("(^|\\s)" + attrShort + "(\\s|$)").test(normalized);
}

function getEffectiveConfigDetails(elt) {
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
        found = {
          value: node.getAttribute(attrName),
          source: node === elt ? "direct" : "inherited",
          element: desc(node),
          blockedBy: "",
        };
        break;
      }
      var disinherit = (node.getAttribute && node.getAttribute("hx-disinherit")) || "";
      if (disinherits(disinherit, attrName, attrShort)) {
        found = {
          value: "(default)",
          source: "blocked",
          element: desc(node),
          blockedBy: disinherit,
        };
        break;
      }
      node = node.parentElement;
    }
    result[attrName] = found !== null ? found : {
      value: "(default)",
      source: "default",
      element: "",
      blockedBy: "",
    };
  }
  return result;
}

function getEffectiveConfig(elt) {
  var details = getEffectiveConfigDetails(elt);
  var result = {};
  for (var k in details) {
    if (!Object.prototype.hasOwnProperty.call(details, k)) continue;
    result[k] = details[k].value;
  }
  return result;
}

function formatConfig(cfg) {
  var lines = [];
  for (var k in cfg) lines.push(k + ": " + cfg[k]);
  return lines.join("\n");
}

function formatConfigDetails(details) {
  var lines = [];
  for (var k in details) {
    if (!Object.prototype.hasOwnProperty.call(details, k)) continue;
    var d = details[k];
    var line = k + ": " + d.value;
    if (d.source && d.source !== "default") {
      line += " [" + d.source;
      if (d.element) line += " from " + d.element;
      if (d.blockedBy) line += " by hx-disinherit=\"" + d.blockedBy + "\"";
      line += "]";
    }
    lines.push(line);
  }
  return lines.join("\n");
}

function shellQuote(s) {
  if (s == null) return "''";
  return "'" + String(s).replace(/'/g, "'\\''") + "'";
}

function readResponseHeader(response, name) {
  if (!response) return null;
  if (response.headers && typeof response.headers.get === "function") {
    return response.headers.get(name);
  }
  return response.getResponseHeader ? response.getResponseHeader(name) : null;
}

function parseResponseHeaders(response) {
  var out = {};
  if (response && response.headers && typeof response.headers.forEach === "function") {
    response.headers.forEach(function(value, name) {
      out[String(name).toLowerCase()] = String(value);
    });
    return out;
  }
  var raw = response && response.getAllResponseHeaders && response.getAllResponseHeaders();
  if (!raw) return out;
  raw.trim().split(/[\r\n]+/).forEach(function(line) {
    var idx = line.indexOf(":");
    if (idx === -1) return;
    var name = line.slice(0, idx).trim().toLowerCase();
    var val = line.slice(idx + 1).trim();
    out[name] = val;
  });
  return out;
}

function copyRequestHeaders(headers) {
  var out = {};
  if (!headers) return out;
  if (typeof headers.forEach === "function") {
    headers.forEach(function(value, name) { out[name] = value; });
    return out;
  }
  for (var name in headers) {
    if (Object.prototype.hasOwnProperty.call(headers, name)) out[name] = headers[name];
  }
  return out;
}

function readRequestHeader(headers, name) {
  if (!headers) return null;
  if (headers[name] != null) return headers[name];
  var wanted = String(name).toLowerCase();
  for (var key in headers) {
    if (Object.prototype.hasOwnProperty.call(headers, key) && String(key).toLowerCase() === wanted) {
      return headers[key];
    }
  }
  return null;
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

function responseContainsSelector(html, selector) {
  if (!html || !selector || selector === "(default)") return null;
  try {
    var doc = new DOMParser().parseFromString(String(html), "text/html");
    return !!doc.querySelector(selector);
  } catch (e) {
    if (selector.charAt(0) === "#" && selector.indexOf(" ") < 0) {
      var id = selector.slice(1).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      return new RegExp("id\\s*=\\s*[\"']" + id + "[\"']").test(String(html));
    }
    return null;
  }
}

function looksLikeFullDocument(html) {
  if (!html) return false;
  return /<!doctype\s+html\b|<html[\s>]/i.test(String(html));
}

function isMutatingMethod(method) {
  return /^(POST|PUT|PATCH|DELETE)$/i.test(String(method || ""));
}

function detailLine(label, value, source) {
  var line = label + ": " + (value || "(none)");
  if (source && source !== "default") line += " [" + source + "]";
  return line;
}

function buildSwapDoctor(r) {
  var lines = [];
  var warnings = [];
  var details = r.effectiveConfigDetails || (r.elt ? getEffectiveConfigDetails(r.elt) : {});
  var target = details["hx-target"] || { value: "(default)", source: "default" };
  var select = details["hx-select"] || { value: "(default)", source: "default" };
  var swap = details["hx-swap"] || { value: "(default)", source: "default" };
  var trigger = details["hx-trigger"] || { value: "(default)", source: "default" };

  lines.push(detailLine("Effective target", target.value, target.source));
  lines.push(detailLine("Effective select", select.value, select.source));
  lines.push(detailLine("Effective swap", swap.value, swap.source));
  lines.push(detailLine("Effective trigger", trigger.value, trigger.source));
  lines.push("Recorded target: " + (r.target || "(not recorded)"));
  if (r.targetBefore) lines.push("Target before swap: " + r.targetBefore);
  if (r.renderIntent) lines.push("Chirp intent: " + r.renderIntent);
  if (r.renderPlan) {
    lines.push("Render plan: " + (r.renderPlan.intent || "?") + " " +
      (r.renderPlan.template || "?") + " -> " + (r.renderPlan.block || "(full)"));
  }
  if (r.selectMatched !== undefined && r.selectMatched !== null) {
    lines.push("Response contains " + r.select + ": " + (r.selectMatched ? "yes" : "no"));
  }

  if (r.status != null && r.status >= 400) {
    warnings.push("Response status " + r.status + " means htmx may use an error path instead of swapping normally.");
  }
  if (r.targetExistsBefore === false) {
    warnings.push("No target was recorded before swap. Check hx-target inheritance and whether the element exists in the current fragment.");
  }
  if (r.selectMatched === false) {
    warnings.push("The response did not contain effective hx-select " + r.select + "; htmx can blank the target when inherited selectors miss.");
  }
  if (looksLikeFullDocument(r.bodyPreview) && r.requestHeaders && r.requestHeaders["HX-Request"] && r.renderIntent !== "full_page") {
    warnings.push("A full HTML document arrived for an htmx request. Return Page/Fragment with the intended block or adjust hx-select.");
  }
  if (isMutatingMethod(r.method) && target.source === "inherited" && /#main|#page-content/.test(target.value || "")) {
    warnings.push("A mutating request inherits broad target " + target.value + ". Prefer a local target or an Action/FormAction response.");
  }
  if (r.domBefore != null && r.domAfter != null && r.domBefore === r.domAfter) {
    warnings.push("The swap completed but the target HTML did not change.");
  }
  if (!r.renderPlan && r.renderIntent) {
    warnings.push("Render intent was present but no render plan header was decoded.");
  }

  return {
    ok: warnings.length === 0,
    lines: lines,
    warnings: warnings,
  };
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
