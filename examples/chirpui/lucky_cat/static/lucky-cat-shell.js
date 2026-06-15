/* Lucky Cat shell — cookie-persisted rail collapse for the progressive rail
   (#231).

   The inner contextual rail collapses to the bare icon rail via a discoverable
   toggle button (`[data-luckycat-rail-toggle]`). It is a click-toggle, NOT a
   continuous drag-resizer: a first-class resizable rail belongs in the chirp-ui
   peer package, not hand-rolled in an example (see #231's locked decision).

   The collapse boolean is cookie-persisted (`luckycat_rail_collapsed`) and ALSO
   read server-side (shell.py + the head_extra pre-collapse <style>) so the first
   paint already reflects the collapsed state — no flash. The cookie is
   namespaced so it never collides with chirp-ui's `chirpui-sidebar-collapsed`
   (localStorage).

   The toggle ships INSIDE the rail (sidebar_content), so it is replaced on every
   boosted OOB sidebar swap. We delegate the click off the document (survives
   swaps) and re-sync the collapsed class + toggle aria-expanded on
   htmx:afterSwap / htmx:afterSettle (kanban/elbysodic idiom). */
(function () {
  "use strict";

  // Document-delegated handlers can fire with event.target === document (or
  // window) — neither has .closest(), which would throw "closest is not a
  // function". Guard every delegated lookup: return null unless target is an
  // Element.
  function elClosest(target, selector) {
    return target && typeof target.closest === "function"
      ? target.closest(selector)
      : null;
  }

  var COLLAPSED_COOKIE = "luckycat_rail_collapsed";
  var COLLAPSED_CLASS = "luckycat-rail--collapsed";
  var YEAR_SECONDS = 60 * 60 * 24 * 365;

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
    /* Once JS owns the state, retire the server pre-collapse <style> so the
       runtime collapsed class is the only thing driving the layout. */
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

  /* Reflect the collapsed boolean onto the shell + toggles, and persist it. */
  function setCollapsed(collapsed, persist) {
    var shell = shellEl();
    if (shell) {
      shell.classList.toggle(COLLAPSED_CLASS, collapsed);
    }
    disableServerStyle();
    syncToggles(collapsed);
    if (persist) {
      writeCookie(COLLAPSED_COOKIE, collapsed ? "true" : "false");
    }
  }

  function toggleCollapsed() {
    setCollapsed(!isCollapsed(), true);
  }

  /* Reconcile the runtime state (shell class + toggle aria) with the persisted
     cookie without a reload — the server already applied the pre-collapse
     <style>. Also runs after boosted OOB rail swaps so the re-shipped toggle is
     authoritative. */
  function sync() {
    setCollapsed(isCollapsed(), false);
  }

  /* The VISIBLE, discoverable collapse/expand control. Delegated off the
     document so it survives the boosted OOB rail swap (the button re-ships in
     the swapped rail). A real <button> handles Enter/Space natively, so no
     keyboard special-casing is needed here. */
  document.addEventListener("click", function (event) {
    var toggle = elClosest(event.target, "[data-luckycat-rail-toggle]");
    if (toggle) {
      event.preventDefault();
      toggleCollapsed();
    }
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", sync);
  } else {
    sync();
  }

  document.body.addEventListener("htmx:afterSwap", sync);
  document.body.addEventListener("htmx:afterSettle", sync);
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
