// --- inspector.js — Element inspector overlay ---

var overlayEl, tooltipEl, highlightEl, pinnedEl;

function buildTooltip(el, pinRect) {
  var cfg = getEffectiveConfigDetails(el);
  var hasHx = Object.keys(cfg).some(function(k) { return cfg[k].value !== "(default)"; });
  if (!hasHx && !pinRect) {
    tooltipEl.style.display = "none";
    return;
  }
  var lines = [desc(el)];
  for (var k in cfg) {
    var d = cfg[k];
    var suffix = "";
    if (!pinRect && d.source && d.source !== "default") {
      suffix = " (" + d.source + (d.element ? " from " + d.element : "") + ")";
    }
    lines.push(k + ": " + d.value + suffix);
  }
  tooltipEl.textContent = lines.join("\n");
  tooltipEl.style.display = "block";
  if (pinRect) {
    tooltipEl.style.left = (pinRect.right + 10) + "px";
    tooltipEl.style.top = pinRect.top + "px";
  }
  if (!tooltipEl.parentNode) overlayEl.appendChild(tooltipEl);
}

function positionHighlight(el) {
  var rect = el.getBoundingClientRect();
  highlightEl.style.cssText = "position:fixed;left:" + rect.left + "px;top:" + rect.top + "px;width:" + rect.width + "px;height:" + rect.height + "px;";
  highlightEl.style.display = "block";
  if (!highlightEl.parentNode) overlayEl.appendChild(highlightEl);
  return rect;
}

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
    positionHighlight(el);
    buildTooltip(el, null);
    if (tooltipEl.style.display !== "none") {
      tooltipEl.style.left = (e.clientX + 15) + "px";
      tooltipEl.style.top = (e.clientY + 15) + "px";
    }
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
    var rect = positionHighlight(el);
    buildTooltip(el, rect);
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
