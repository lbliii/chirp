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
