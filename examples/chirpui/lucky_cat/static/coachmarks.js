/* Lucky Cat first-visit coachmarks (#297).
   A dismissible three-step tour highlighting SSE live regions, 422 form
   re-render, and Suspense portfolio panels. Persists luckycat-tour-seen in
   localStorage (with a cookie mirror for parity with shell.py conventions).
   Cross-page steps resume via sessionStorage after boosted/full navigation. */
(function () {
  "use strict";

  var SEEN_KEY = "luckycat-tour-seen";
  var ACTIVE_KEY = "luckycat-tour-active";
  var STEP_KEY = "luckycat-tour-step";
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

  function tourSeen() {
    try {
      if (localStorage.getItem(SEEN_KEY) === "1") return true;
    } catch (_err) {}
    return readCookie(SEEN_KEY) === "1";
  }

  function markSeen() {
    try {
      localStorage.setItem(SEEN_KEY, "1");
    } catch (_err) {}
    writeCookie(SEEN_KEY, "1");
    try {
      sessionStorage.removeItem(ACTIVE_KEY);
      sessionStorage.removeItem(STEP_KEY);
    } catch (_err2) {}
  }

  function isAuthenticated() {
    var root = document.getElementById("luckycat-tour");
    return root && root.getAttribute("data-tour-auth") === "true";
  }

  function stepsForUser() {
    var all = [
      {
        selectors: ["#order-book", "#lucky-cat-ticker"],
        title: "Live ticker & order book",
        body: "Updated over SSE, zero JS.",
        href: "/markets/BTC-MEOW",
      },
      {
        selectors: ["#order-form"],
        title: "Trade form validation",
        body: "422 re-render in place.",
        href: "/trade",
        auth: true,
      },
      {
        selectors: [".luckycat-pf-grid"],
        title: "Portfolio dashboard",
        body: "Suspense: shell first, panels stream.",
        href: "/portfolio",
        auth: true,
      },
    ];
    if (!isAuthenticated()) {
      return all.slice(0, 1);
    }
    return all;
  }

  function findTarget(step) {
    for (var i = 0; i < step.selectors.length; i++) {
      var el = document.querySelector(step.selectors[i]);
      if (el) return el;
    }
    return null;
  }

  function rootEl() {
    return document.getElementById("luckycat-tour");
  }

  function positionSpotlight(target, pad) {
    var root = rootEl();
    if (!root || !target) return;
    var spot = root.querySelector(".luckycat-tour__spotlight");
    var card = root.querySelector(".luckycat-tour__card");
    if (!spot || !card) return;
    var rect = target.getBoundingClientRect();
    var inset = pad || 8;
    spot.style.top = Math.max(0, rect.top - inset) + "px";
    spot.style.left = Math.max(0, rect.left - inset) + "px";
    spot.style.width = rect.width + inset * 2 + "px";
    spot.style.height = rect.height + inset * 2 + "px";

    var cardRect = card.getBoundingClientRect();
    var top = rect.bottom + 16;
    if (top + cardRect.height > window.innerHeight - 12) {
      top = Math.max(12, rect.top - cardRect.height - 16);
    }
    var left = rect.left + rect.width / 2 - cardRect.width / 2;
    left = Math.max(12, Math.min(window.innerWidth - cardRect.width - 12, left));
    card.style.top = top + "px";
    card.style.left = left + "px";
  }

  function renderStep(index, steps) {
    var root = rootEl();
    if (!root) return;
    var step = steps[index];
    if (!step) {
      finish();
      return;
    }
    var target = findTarget(step);
    if (!target && step.href && location.pathname !== step.href.split("?")[0]) {
      try {
        sessionStorage.setItem(ACTIVE_KEY, "1");
        sessionStorage.setItem(STEP_KEY, String(index));
      } catch (_err) {}
      window.location.assign(step.href);
      return;
    }
    if (!target) {
      finish();
      return;
    }

    root.hidden = false;
    root.setAttribute("data-step", String(index));
    document.documentElement.classList.add("luckycat-tour--open");

    var title = root.querySelector(".luckycat-tour__title");
    var body = root.querySelector(".luckycat-tour__body");
    var counter = root.querySelector(".luckycat-tour__counter");
    var back = root.querySelector(".luckycat-tour__back");
    var next = root.querySelector(".luckycat-tour__next");
    if (title) title.textContent = step.title;
    if (body) body.textContent = step.body;
    if (counter) counter.textContent = "Step " + (index + 1) + " of " + steps.length;
    if (back) back.hidden = index === 0;
    if (next) next.textContent = index === steps.length - 1 ? "Done" : "Next";

    target.scrollIntoView({ block: "nearest", behavior: "auto" });
    positionSpotlight(target, 8);
    try {
      sessionStorage.setItem(ACTIVE_KEY, "1");
      sessionStorage.setItem(STEP_KEY, String(index));
    } catch (_err) {}
  }

  function finish() {
    var root = rootEl();
    if (root) root.hidden = true;
    document.documentElement.classList.remove("luckycat-tour--open");
    markSeen();
  }

  function startIndex() {
    try {
      if (sessionStorage.getItem(ACTIVE_KEY) === "1") {
        var saved = parseInt(sessionStorage.getItem(STEP_KEY) || "0", 10);
        if (!isNaN(saved)) return saved;
      }
    } catch (_err) {}
    return 0;
  }

  function bindControls(steps) {
    var root = rootEl();
    if (!root || root.getAttribute("data-bound") === "1") return;
    root.setAttribute("data-bound", "1");
    var index = startIndex();

    function go(delta) {
      index = Math.max(0, Math.min(steps.length - 1, index + delta));
      renderStep(index, steps);
    }

    root.addEventListener("click", function (event) {
      var skip = event.target.closest(".luckycat-tour__skip");
      var back = event.target.closest(".luckycat-tour__back");
      var next = event.target.closest(".luckycat-tour__next");
      var backdrop = event.target.closest(".luckycat-tour__backdrop");
      if (skip || backdrop) {
        event.preventDefault();
        finish();
        return;
      }
      if (back) {
        event.preventDefault();
        go(-1);
        return;
      }
      if (next) {
        event.preventDefault();
        if (index >= steps.length - 1) {
          finish();
        } else {
          index += 1;
          renderStep(index, steps);
        }
      }
    });

    window.addEventListener("resize", function () {
      if (root.hidden) return;
      var step = steps[index];
      var target = step ? findTarget(step) : null;
      if (target) positionSpotlight(target, 8);
    });

    if (!tourSeen()) {
      renderStep(index, steps);
    }
  }

  function boot() {
    if (tourSeen()) return;
    if (location.pathname === "/login") return;
    var steps = stepsForUser();
    if (!steps.length) return;
    bindControls(steps);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
