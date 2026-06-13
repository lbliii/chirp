/* Lucky Cat shell — genuine continuous drag-resize for the progressive rail
   (#231, BUILD 2).

   The rail-edge handle (`.luckycat-sidebar-resize`, role="separator",
   cursor: ew-resize) is a REAL pointer-drag resizer, not a click-toggle: drag it
   to set a continuous `--luckycat-rail-width` (the inner contextual rail's
   width); double-click to collapse/expand to the bare icon rail; arrow keys nudge
   the width and Home/End collapse/expand for keyboard parity.

   Two preferences are cookie-persisted and ALSO read server-side (shell.py + the
   head_extra pre-sized <style>) so the first paint already reflects the dragged
   width and collapse state — no flash:

     * luckycat_rail_width    — the dragged inner-rail width in CSS px (int)
     * luckycat_rail_collapsed — the collapse boolean ("true"/"false")

   Both cookies are namespaced so they never collide with chirp-ui's
   `chirpui-sidebar-collapsed` (localStorage) or elbysodic's key. The width cookie
   the server reflects into a <style> is parsed+clamped on the server too, so a
   tampered value can never reach the CSS sink.

   The handle ships INSIDE the rail (sidebar_content), so it is replaced on every
   boosted OOB sidebar swap. We delegate pointer/keyboard events off the document
   (survives swaps) and re-sync handle aria-valuenow + the collapsed class on
   htmx:afterSwap / htmx:afterSettle (kanban/elbysodic idiom). */
(function () {
  "use strict";

  // Document-delegated handlers (pointerleave/lostpointercapture/click) can fire
  // with event.target === document (or window) — neither has .closest(), which
  // threw "event.target.closest is not a function" and broke the shell JS. Guard
  // every delegated lookup: return null unless the target is an Element.
  function elClosest(target, selector) {
    return target && typeof target.closest === "function"
      ? target.closest(selector)
      : null;
  }

  var WIDTH_COOKIE = "luckycat_rail_width";
  var COLLAPSED_COOKIE = "luckycat_rail_collapsed";
  var COLLAPSED_CLASS = "luckycat-rail--collapsed";
  var DRAGGING_CLASS = "luckycat-rail--dragging";
  var WIDTH_VAR = "--luckycat-rail-width";
  var YEAR_SECONDS = 60 * 60 * 24 * 365;

  /* Drag clamp (CSS px). MUST mirror shell.py RAIL_WIDTH_MIN_PX/MAX_PX and the
     handle's aria-valuemin/aria-valuemax so server, client, and ARIA agree. */
  var MIN_PX = 176;
  var MAX_PX = 416;
  /* Collapsed inner-rail width (icon-rail only); the drag-start basis when
     expanding out from the collapsed state. (aria-valuenow is reported as
     MIN_PX when collapsed so it stays within the declared valuemin/max range.) */
  var COLLAPSED_PX = 68;
  /* Keyboard nudge step. */
  var STEP_PX = 24;

  function clamp(px) {
    return Math.max(MIN_PX, Math.min(MAX_PX, Math.round(px)));
  }

  function readCookie(name) {
    var match = document.cookie.match(new RegExp("(^|; )" + name + "=([^;]*)"));
    return match ? decodeURIComponent(match[2]) : null;
  }

  function writeCookie(name, value) {
    var secure = window.location.protocol === "https:" ? "; Secure" : "";
    document.cookie =
      name + "=" + value + "; Max-Age=" + YEAR_SECONDS + "; Path=/; SameSite=Lax" + secure;
  }

  function disableServerStyle() {
    /* Once JS owns the state, retire the server pre-sized/pre-collapse <style> so
       the runtime CSS var + class are the only things driving the layout. */
    var serverStyle = document.getElementById("luckycat-rail-cookie-state");
    if (serverStyle) {
      serverStyle.disabled = true;
    }
  }

  function shellEl() {
    return document.querySelector(".chirpui-app-shell");
  }

  function isCollapsed() {
    var shell = shellEl();
    if (shell && shell.classList.contains(COLLAPSED_CLASS)) {
      return true;
    }
    return readCookie(COLLAPSED_COOKIE) === "true";
  }

  /* The current effective inner-rail width in px. Prefer the persisted cookie;
     fall back to the computed value of --luckycat-rail-width (handles the CSS
     clamp() default before the user has ever dragged). */
  function currentWidth() {
    var cookie = readCookie(WIDTH_COOKIE);
    if (cookie !== null) {
      var parsed = parseInt(cookie, 10);
      if (!isNaN(parsed)) {
        return clamp(parsed);
      }
    }
    var raw = getComputedStyle(document.documentElement).getPropertyValue(WIDTH_VAR);
    var computed = parseFloat(raw);
    if (!isNaN(computed)) {
      return clamp(computed);
    }
    return clamp(256);
  }

  function applyWidth(px) {
    document.documentElement.style.setProperty(WIDTH_VAR, px + "px");
  }

  function syncHandles(valueNow) {
    /* aria-valuenow must stay within [valuemin, valuemax]. The collapsed state
       (icon-rail only) is narrower than MIN_PX, so clamp to keep the ARIA range
       valid; the collapse itself is conveyed by the shell's collapsed class. */
    var v = Math.max(MIN_PX, Math.min(MAX_PX, Math.round(valueNow)));
    var handles = document.querySelectorAll("[data-luckycat-rail-resize]");
    for (var i = 0; i < handles.length; i++) {
      handles[i].setAttribute("aria-valuenow", String(v));
    }
  }

  /* Reflect the collapsed boolean onto every visible collapse TOGGLE button:
     aria-expanded is the inverse of collapsed, and the accessible label flips
     between "Collapse"/"Expand" so a screen reader announces the next action. */
  function syncToggles(collapsed) {
    var toggles = document.querySelectorAll("[data-luckycat-rail-toggle]");
    for (var i = 0; i < toggles.length; i++) {
      toggles[i].setAttribute("aria-expanded", collapsed ? "false" : "true");
      var label = collapsed ? "Expand navigation" : "Collapse navigation";
      toggles[i].setAttribute("aria-label", label);
      toggles[i].setAttribute("title", label);
    }
  }

  /* Reflect the collapsed boolean onto the shell + handles + toggles, and
     persist it. */
  function setCollapsed(collapsed, persist) {
    var shell = shellEl();
    if (shell) {
      shell.classList.toggle(COLLAPSED_CLASS, collapsed);
    }
    disableServerStyle();
    syncHandles(collapsed ? MIN_PX : currentWidth());
    syncToggles(collapsed);
    if (persist) {
      writeCookie(COLLAPSED_COOKIE, collapsed ? "true" : "false");
    }
  }

  function toggleCollapsed() {
    setCollapsed(!isCollapsed(), true);
  }

  /* Apply a new dragged width: clamp, write the CSS var + aria-valuenow, and (on
     commit) persist the width cookie. Dragging implies expanded, so clear any
     collapsed state when the user resizes. */
  function setWidth(px, persist) {
    var width = clamp(px);
    if (isCollapsed()) {
      setCollapsed(false, persist);
    }
    applyWidth(width);
    disableServerStyle();
    syncHandles(width);
    if (persist) {
      writeCookie(WIDTH_COOKIE, String(width));
    }
    return width;
  }

  /* ------------------------------------------------------------------ drag --- */

  var drag = null; /* { handle, pointerId, startX, startWidth } */

  function onPointerDown(event) {
    var handle = elClosest(event.target,"[data-luckycat-rail-resize]");
    if (!handle || event.button !== 0) {
      return;
    }
    event.preventDefault();
    drag = {
      handle: handle,
      pointerId: event.pointerId,
      startX: event.clientX,
      startWidth: isCollapsed() ? COLLAPSED_PX : currentWidth(),
    };
    /* Suspend the grid-template-columns transition for 1:1 pointer tracking. */
    var shell = shellEl();
    if (shell) {
      shell.classList.add(DRAGGING_CLASS);
    }
    try {
      handle.setPointerCapture(event.pointerId);
    } catch (_err) {
      /* setPointerCapture is best-effort; the document listeners still drive. */
    }
  }

  function onPointerMove(event) {
    if (!drag) {
      return;
    }
    var dx = event.clientX - drag.startX;
    setWidth(drag.startWidth + dx, false);
  }

  function endDrag(event) {
    if (!drag) {
      return;
    }
    var dx = event.clientX - drag.startX;
    setWidth(drag.startWidth + dx, true); /* commit + persist */
    try {
      drag.handle.releasePointerCapture(drag.pointerId);
    } catch (_err) {
      /* ignore */
    }
    var shell = shellEl();
    if (shell) {
      shell.classList.remove(DRAGGING_CLASS);
    }
    drag = null;
  }

  /* --------------------------------------------------------------- keyboard --- */

  function onKeyDown(event) {
    var handle = elClosest(event.target,"[data-luckycat-rail-resize]");
    if (!handle) {
      return;
    }
    switch (event.key) {
      case "ArrowLeft":
        event.preventDefault();
        setWidth(currentWidth() - STEP_PX, true);
        break;
      case "ArrowRight":
        event.preventDefault();
        setWidth(currentWidth() + STEP_PX, true);
        break;
      case "Home":
        event.preventDefault();
        setWidth(MIN_PX, true);
        break;
      case "End":
        event.preventDefault();
        setWidth(MAX_PX, true);
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        toggleCollapsed();
        break;
      default:
        break;
    }
  }

  /* ----------------------------------------------------------------- wiring --- */

  function init() {
    /* Reconcile the runtime state with the persisted cookies so the handle ARIA,
       the toggle aria-expanded, and the collapsed class are authoritative without
       a reload (the server already applied the pre-sized/pre-collapse <style>). */
    if (isCollapsed()) {
      setCollapsed(true, false);
    } else {
      syncHandles(currentWidth());
      syncToggles(false);
    }
  }

  /* Delegate off the document so the handle survives OOB rail swaps. */
  document.addEventListener("pointerdown", onPointerDown);
  document.addEventListener("pointermove", onPointerMove);
  document.addEventListener("pointerup", endDrag);
  document.addEventListener("lostpointercapture", function (event) {
    /* If capture is lost mid-drag (e.g. context menu), commit at the last X. */
    if (drag) {
      endDrag(event);
    }
  });
  document.addEventListener("dblclick", function (event) {
    var handle = elClosest(event.target,"[data-luckycat-rail-resize]");
    if (handle) {
      event.preventDefault();
      toggleCollapsed();
    }
  });
  /* The VISIBLE, discoverable collapse/expand control. Delegated off the
     document so it survives the boosted OOB rail swap (the button re-ships in
     the swapped rail). A real <button> handles Enter/Space natively, so no
     keyboard special-casing is needed here. */
  document.addEventListener("click", function (event) {
    var toggle = elClosest(event.target,"[data-luckycat-rail-toggle]");
    if (toggle) {
      event.preventDefault();
      toggleCollapsed();
    }
  });
  document.addEventListener("keydown", onKeyDown);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  /* The rail is OOB-swapped on boosted nav; re-seed the new handle's ARIA +
     collapsed class after the swap settles. */
  function resync() {
    if (isCollapsed()) {
      setCollapsed(true, false);
    } else {
      syncHandles(currentWidth());
      syncToggles(false);
    }
  }
  document.body.addEventListener("htmx:afterSwap", resync);
  document.body.addEventListener("htmx:afterSettle", resync);
})();

/* Lucky Cat hero-chart crosshair — a lightweight hover/focus reticle over the
   signature area chart (no chart lib, no Alpine).

   The chart figure carries data-luckycat-chart and data-chart-points="<island
   id>", pointing at a nonced <script type="application/json"> island whose
   payload is the per-sample geometry: [[x, y, price, label], ...] in the SVG's
   100x36 viewBox space (x: 0..100, y: 0..36). On pointermove / focus we map the
   cursor's fractional x across the figure to the nearest sample, snap the SVG
   crosshair <line> to that sample's x, and fill the price/time tooltip — pure
   read-only DOM, JSON.parse only (no eval). The tooltip is positioned with
   percentage left so it tracks under the stretched viewBox.

   Delegated off the document so it survives boosted/OOB swaps (the chart region
   is re-rendered whole by the timeframe toggle). Reduced motion: the crosshair
   snap is instant by default; the optional fade is gated in CSS on
   prefers-reduced-motion, so this controller adds no motion of its own. */
(function () {
  "use strict";

  // The pointerleave handler is registered on document with capture, so when the
  // pointer leaves the viewport event.target is the document — which has no
  // .closest(). Guard every delegated lookup (see the shell IIFE above).
  function elClosest(target, selector) {
    return target && typeof target.closest === "function"
      ? target.closest(selector)
      : null;
  }

  function parsePoints(figure) {
    var islandId = figure.getAttribute("data-chart-points");
    if (!islandId) {
      return null;
    }
    var island = document.getElementById(islandId);
    if (!island) {
      return null;
    }
    try {
      var data = JSON.parse(island.textContent || "[]");
      return Array.isArray(data) && data.length ? data : null;
    } catch (_err) {
      return null;
    }
  }

  function nearestIndex(points, fracX) {
    /* points x are in 0..100 viewBox space; fracX is 0..1 across the figure. */
    var targetX = fracX * 100;
    var best = 0;
    var bestDist = Infinity;
    for (var i = 0; i < points.length; i++) {
      var dist = Math.abs(points[i][0] - targetX);
      if (dist < bestDist) {
        bestDist = dist;
        best = i;
      }
    }
    return best;
  }

  function show(figure, point) {
    var line = figure.querySelector("[data-luckycat-crosshair]");
    var tip = figure.querySelector("[data-luckycat-chart-tip]");
    if (line) {
      line.setAttribute("x1", String(point[0]));
      line.setAttribute("x2", String(point[0]));
      line.removeAttribute("hidden");
    }
    if (tip) {
      var priceEl = tip.querySelector("[data-luckycat-chart-tip-price]");
      var timeEl = tip.querySelector("[data-luckycat-chart-tip-time]");
      if (priceEl) {
        priceEl.textContent = String(point[2]);
      }
      if (timeEl) {
        timeEl.textContent = String(point[3]);
      }
      /* Position as a percentage of the figure width so it tracks the stretched
         viewBox; clamp so the tooltip never overflows the figure edges. */
      var pct = Math.max(4, Math.min(96, point[0]));
      tip.style.left = pct + "%";
      tip.removeAttribute("hidden");
    }
  }

  function hide(figure) {
    var line = figure.querySelector("[data-luckycat-crosshair]");
    var tip = figure.querySelector("[data-luckycat-chart-tip]");
    if (line) {
      line.setAttribute("hidden", "");
    }
    if (tip) {
      tip.setAttribute("hidden", "");
    }
  }

  function track(event) {
    var figure = elClosest(event.target,"[data-luckycat-chart]");
    if (!figure) {
      return;
    }
    var points = parsePoints(figure);
    if (!points) {
      return;
    }
    var rect = figure.getBoundingClientRect();
    if (rect.width <= 0) {
      return;
    }
    var fracX = (event.clientX - rect.left) / rect.width;
    fracX = Math.max(0, Math.min(1, fracX));
    show(figure, points[nearestIndex(points, fracX)]);
  }

  function leave(event) {
    var figure = elClosest(event.target,"[data-luckycat-chart]");
    if (figure) {
      hide(figure);
    }
  }

  document.addEventListener("pointermove", track);
  document.addEventListener("pointerleave", leave, true);
  /* Keyboard parity: focusing the figure snaps the reticle to the latest
     (newest) sample so keyboard users get the current readout. */
  document.addEventListener(
    "focusin",
    function (event) {
      var figure = elClosest(event.target,"[data-luckycat-chart]");
      if (!figure) {
        return;
      }
      var points = parsePoints(figure);
      if (points) {
        show(figure, points[points.length - 1]);
      }
    },
    true
  );
  document.addEventListener(
    "focusout",
    function (event) {
      var figure = elClosest(event.target,"[data-luckycat-chart]");
      if (figure && !figure.contains(event.relatedTarget)) {
        hide(figure);
      }
    },
    true
  );
})();
