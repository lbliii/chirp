// --- highlight.js — Client-side syntax highlighting (Tokyo Night palette) ---

var HL = {
  str: "#9ece6a",
  num: "#ff9e64",
  bool: "#bb9af7",
  key: "#7aa2f7",
  tag: "#f7768e",
  attr: "#bb9af7",
  comment: "#565f89",
  add: "rgba(158,206,106,.15)",
  del: "rgba(247,118,142,.15)",
  header: "#7aa2f7",
};

function hlJSON(s) {
  return s.replace(
    /("(?:[^"\\]|\\.)*")\s*:/g,
    '<span style="color:' + HL.key + '">$1</span>:'
  ).replace(
    /:\s*("(?:[^"\\]|\\.)*")/g,
    ': <span style="color:' + HL.str + '">$1</span>'
  ).replace(
    /:\s*(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g,
    ': <span style="color:' + HL.num + '">$1</span>'
  ).replace(
    /:\s*(true|false|null)\b/g,
    ': <span style="color:' + HL.bool + '">$1</span>'
  );
}

function hlHeaders(s) {
  return s.split("\n").map(function(line) {
    var idx = line.indexOf(":");
    if (idx < 1) return esc(line);
    var name = line.slice(0, idx);
    var val = line.slice(idx + 1);
    return '<span style="color:' + HL.header + '">' + esc(name) + '</span>:' + esc(val);
  }).join("\n");
}

function hlDiff(lines) {
  return lines.map(function(l) {
    if (l.charAt(0) === "+") return '<span style="background:' + HL.add + ';display:block">' + esc(l) + '</span>';
    if (l.charAt(0) === "-") return '<span style="background:' + HL.del + ';display:block">' + esc(l) + '</span>';
    if (l.charAt(0) === "@") return '<span style="color:' + HL.bool + '">' + esc(l) + '</span>';
    return esc(l);
  }).join("\n");
}

function diffLines(a, b) {
  var aLines = a.split("\n");
  var bLines = b.split("\n");
  if (aLines.length > 500 || bLines.length > 500) {
    return ["@@ diff too large (" + aLines.length + " vs " + bLines.length + " lines) @@"];
  }
  var aSet = {};
  var bSet = {};
  for (var i = 0; i < aLines.length; i++) aSet[aLines[i]] = (aSet[aLines[i]] || 0) + 1;
  for (var j = 0; j < bLines.length; j++) bSet[bLines[j]] = (bSet[bLines[j]] || 0) + 1;

  var result = [];
  var added = 0, removed = 0;
  for (var k = 0; k < aLines.length; k++) {
    if (!bSet[aLines[k]] || bSet[aLines[k]] <= 0) {
      result.push("- " + aLines[k]);
      removed++;
    } else {
      bSet[aLines[k]]--;
      result.push("  " + aLines[k]);
    }
  }
  for (var m = 0; m < bLines.length; m++) {
    var found = false;
    for (var n = 0; n < aLines.length; n++) {
      if (aLines[n] === bLines[m]) { aLines[n] = null; found = true; break; }
    }
    if (!found) {
      result.push("+ " + bLines[m]);
      added++;
    }
  }
  if (added === 0 && removed === 0) return ["(no changes)"];
  result.unshift("@@ -" + (aLines.length - added) + " +" + (bLines.length - removed) + " @@ " + added + " added, " + removed + " removed");
  return result;
}

function decodeRenderPlan(encoded) {
  try {
    var json = atob(encoded);
    return JSON.parse(json);
  } catch (e) {
    return null;
  }
}

function formatRenderPlan(plan) {
  if (!plan) return "(no render plan)";
  var parts = [];
  parts.push("Intent: " + (plan.intent || "unknown"));
  if (plan.template) parts.push("Template: " + plan.template);
  if (plan.block) parts.push("Block: " + plan.block);
  if (plan.layouts_applied && plan.layouts_applied.length) {
    parts.push("Layouts applied (start=" + (plan.layout_start || 0) + "):");
    plan.layouts_applied.forEach(function(l) { parts.push("  " + l); });
  }
  if (plan.regions && plan.regions.length) {
    parts.push("Shell region updates:");
    plan.regions.forEach(function(r) {
      parts.push("  " + r.region + " \u2190 " + r.template + (r.block ? ":" + r.block : "") + " [" + r.mode + "]");
    });
  }
  if (plan.context_keys && plan.context_keys.length) {
    parts.push("Context keys (" + plan.context_keys.length + "): " + plan.context_keys.join(", "));
  }
  if (plan.include_layout_oob) parts.push("include_layout_oob: true");
  return parts.join("\n");
}

function renderRenderPlanHTML(plan) {
  if (!plan) return '<span style="color:#565f89">(no render plan)</span>';

  // Intent badge
  var intentColors = {
    full_page: COLORS.success,
    page_fragment: COLORS.info,
    local_fragment: COLORS.warning
  };
  var intentColor = intentColors[plan.intent] || COLORS.text;
  var html = '<div style="margin-bottom:10px">';
  html += '<span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:bold;background:' + intentColor + '20;color:' + intentColor + ';border:1px solid ' + intentColor + '40">' + esc(plan.intent || "unknown") + '</span>';

  // Flags
  var flags = [];
  if (plan.render_full_template) flags.push("full_template");
  if (plan.apply_layouts) flags.push("apply_layouts");
  if (plan.include_layout_oob) flags.push("layout_oob");
  if (flags.length) {
    html += ' <span style="color:#565f89;font-size:11px">' + flags.join(" \u00b7 ") + '</span>';
  }
  html += '</div>';

  // Template + Block
  html += '<div style="margin-bottom:8px">';
  html += '<span style="color:#565f89;font-size:11px;text-transform:uppercase;letter-spacing:.5px">View</span><br>';
  html += '<span style="color:' + HL.str + '">' + esc(plan.template || "?") + '</span>';
  html += ' <span style="color:#565f89">\u2192</span> ';
  html += '<span style="color:' + HL.key + '">' + esc(plan.block || "(full)") + '</span>';
  html += '</div>';

  // Layout chain
  if (plan.layout_chain && plan.layout_chain.length) {
    html += '<div style="margin-bottom:8px">';
    html += '<span style="color:#565f89;font-size:11px;text-transform:uppercase;letter-spacing:.5px">Layout Chain</span>';
    if (plan.layout_start > 0) {
      html += ' <span style="color:' + COLORS.warning + ';font-size:11px">(start=' + plan.layout_start + ')</span>';
    }
    html += '<div style="margin-top:4px;display:flex;flex-wrap:wrap;gap:4px;align-items:center">';
    for (var li = 0; li < plan.layout_chain.length; li++) {
      var lay = plan.layout_chain[li];
      var isActive = li >= (plan.layout_start || 0);
      var layStyle = isActive
        ? 'background:#7aa2f720;color:' + COLORS.info + ';border:1px solid ' + COLORS.info + '40'
        : 'background:#1e1f2e;color:#565f89;border:1px solid #333';
      html += '<span style="display:inline-block;padding:2px 6px;border-radius:3px;font-size:11px;' + layStyle + '">';
      html += esc(lay.template);
      if (lay.target) html += ' <span style="opacity:.6">\u2192 #' + esc(lay.target) + '</span>';
      html += '</span>';
      if (li < plan.layout_chain.length - 1) {
        html += '<span style="color:#565f89;font-size:10px">\u203a</span>';
      }
    }
    html += '</div></div>';
  } else if (plan.layouts_applied && plan.layouts_applied.length) {
    // Fallback for old compact format
    html += '<div style="margin-bottom:8px">';
    html += '<span style="color:#565f89;font-size:11px;text-transform:uppercase;letter-spacing:.5px">Layouts Applied</span>';
    html += '<div style="margin-top:4px;display:flex;flex-wrap:wrap;gap:4px;align-items:center">';
    for (var ai = 0; ai < plan.layouts_applied.length; ai++) {
      html += '<span style="display:inline-block;padding:2px 6px;border-radius:3px;font-size:11px;background:#7aa2f720;color:' + COLORS.info + ';border:1px solid ' + COLORS.info + '40">';
      html += esc(plan.layouts_applied[ai]);
      html += '</span>';
      if (ai < plan.layouts_applied.length - 1) {
        html += '<span style="color:#565f89;font-size:10px">\u203a</span>';
      }
    }
    html += '</div></div>';
  }

  // Context
  var ctxList = plan.context || null;
  var ctxKeys = plan.context_keys || null;
  if (ctxList && ctxList.length) {
    html += '<div style="margin-bottom:8px">';
    html += '<span style="color:#565f89;font-size:11px;text-transform:uppercase;letter-spacing:.5px">Context (' + ctxList.length + ')</span>';
    html += '<div style="margin-top:4px;display:flex;flex-wrap:wrap;gap:3px">';
    for (var ci = 0; ci < ctxList.length; ci++) {
      var entry = ctxList[ci];
      html += '<span style="display:inline-block;padding:1px 5px;border-radius:3px;font-size:11px;background:#9ece6a15;border:1px solid #9ece6a30">';
      html += '<span style="color:' + HL.key + '">' + esc(entry.key) + '</span>';
      html += '<span style="color:#565f89;font-size:10px;margin-left:3px">' + esc(entry.type) + '</span>';
      html += '</span>';
    }
    html += '</div></div>';
  } else if (ctxKeys && ctxKeys.length) {
    // Fallback for old compact format
    html += '<div style="margin-bottom:8px">';
    html += '<span style="color:#565f89;font-size:11px;text-transform:uppercase;letter-spacing:.5px">Context Keys (' + ctxKeys.length + ')</span>';
    html += '<div style="margin-top:4px;color:' + HL.key + ';font-size:12px">' + ctxKeys.map(esc).join(', ') + '</div>';
    html += '</div>';
  }

  // Region updates
  if (plan.regions && plan.regions.length) {
    html += '<div>';
    html += '<span style="color:#565f89;font-size:11px;text-transform:uppercase;letter-spacing:.5px">Region Updates (' + plan.regions.length + ')</span>';
    html += '<div style="margin-top:4px">';
    for (var ri = 0; ri < plan.regions.length; ri++) {
      var reg = plan.regions[ri];
      html += '<div style="font-size:12px;padding:2px 0">';
      html += '<span style="color:' + COLORS.oob + '">#' + esc(reg.region) + '</span>';
      html += ' <span style="color:#565f89">\u2190</span> ';
      html += '<span style="color:' + HL.str + '">' + esc(reg.template) + '</span>';
      if (reg.block) html += '<span style="color:#565f89">:</span><span style="color:' + HL.key + '">' + esc(reg.block) + '</span>';
      if (reg.mode) html += ' <span style="color:#565f89;font-size:10px">[' + esc(reg.mode) + ']</span>';
      html += '</div>';
    }
    html += '</div></div>';
  }

  return html;
}
