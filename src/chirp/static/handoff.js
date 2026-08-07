/* Chirp hypermedia handoff — focus after settle (CSP-safe external script).
 * Listens for HX-Trigger-After-Settle / htmx:afterSettle payloads shaped as:
 *   {"chirp:focus": {"target": "#id", "fallback": "#main"}}
 * Also honors data-chirp-focus / data-chirp-focus-fallback on the triggering elt.
 */
(function () {
  "use strict";
  if (window.__chirpHandoffInstalled) return;
  window.__chirpHandoffInstalled = true;

  function resolve(sel) {
    if (!sel || typeof sel !== "string") return null;
    try { return document.querySelector(sel); } catch (_) { return null; }
  }

  function focusTarget(detail) {
    var target = detail && detail.target;
    var fallback = (detail && detail.fallback) || "#main";
    var el = resolve(target) || resolve(fallback);
    if (!el) return;
    if (typeof el.focus === "function") {
      try { el.focus({ preventScroll: true }); }
      catch (_) { el.focus(); }
    }
  }

  function fromEventDetail(detail) {
    if (!detail) return null;
    if (detail["chirp:focus"]) return detail["chirp:focus"];
    if (detail.target || detail.fallback) return detail;
    return null;
  }

  document.body.addEventListener("htmx:afterSettle", function (evt) {
    var detail = fromEventDetail(evt.detail && evt.detail.triggerSpec);
    if (!detail && evt.detail && evt.detail.elt) {
      var elt = evt.detail.elt;
      var t = elt.getAttribute && elt.getAttribute("data-chirp-focus");
      var f = elt.getAttribute && elt.getAttribute("data-chirp-focus-fallback");
      if (t || f) detail = { target: t || "", fallback: f || "#main" };
    }
    if (detail) focusTarget(detail);
  });

  document.body.addEventListener("chirp:focus", function (evt) {
    focusTarget(evt.detail || {});
  });
})();
