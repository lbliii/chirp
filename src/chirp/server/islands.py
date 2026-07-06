"""Framework-agnostic islands runtime bootstrap.

Injects a lightweight browser runtime that discovers ``[data-island]`` roots,
parses serialized props, and emits lifecycle events. Frontend adapters can
listen to these events to mount/unmount framework islands.

It also ships ONE blessed, client-resident primitive: ``optimistic_apply``
(see ``_OPTIMISTIC_ADAPTER_JS``). Mounting ``data-island-primitive``
``optimistic_apply`` Just Works with a contract guarantee — Chirp holds zero
per-client server view state; the rollback baseline is the client's OWN
pre-mutation DOM snapshot, never a server-held copy.
"""

# The blessed ``optimistic_apply`` adapter. Authored as a plain string (NOT an
# f-string) so its JavaScript braces need no escaping; it is spliced verbatim
# into the runtime IIFE below, after ``register`` is defined and before the
# first DOMContentLoaded scan, so the adapter is registered before any mount.
#
# Zero server state by construction: the snapshot/rollback baseline lives in
# tab-local memory (``optimisticInflight`` / ``optimisticRegions``); nothing is
# serialized, persisted, or sent. Reconciliation is the ordinary
# authoritative-fragment swap (last-write-wins). The marker comments and the
# absence of any client->server transport token are asserted by the
# zero-server-state guardrail in ``tests/test_islands.py``.
_OPTIMISTIC_ADAPTER_JS = """
  // >>> optimistic_apply adapter (blessed; client-only; zero server state)
  /* baseline: client-only */
  // The rollback baseline is the client's OWN pre-mutation DOM, snapshotted
  // into tab-local memory below. It is never serialized, never persisted, and
  // never sent over any transport; the server is never told an optimistic
  // apply happened. Reconciliation is the ordinary authoritative-fragment swap
  // (last-write-wins). All logic is document-level and correlated by the htmx
  // request identity (XHR in htmx 2, request context in htmx 4); arming reads
  // the element's props FRESH on each request, so it never depends on per-mount
  // listener state that the runtime tears down on a swap.
  var OPTIMISTIC_ALLOWED = ["addClass", "removeClass", "toggleClass", "setText", "setAttr", "removeAttr", "disable"];
  var optimisticInflight = new Map();    // request identity -> { regionEl }
  var optimisticRegions = new WeakMap(); // regionEl -> baseline entry (tab-local)

  function optimisticTargets(regionEl, op) {
    if (op && typeof op.sel === "string" && op.sel) {
      return Array.prototype.slice.call(regionEl.querySelectorAll(op.sel));
    }
    return [regionEl];
  }

  function optimisticApplyOp(regionEl, triggerEl, op) {
    // Apply one reversible op; return a reverter capturing the client's prior
    // state, or null to skip. Each op restores from the live DOM, not a server
    // copy.
    var name = op && op.op;
    if (name === "disable") {
      var prevDisabled = triggerEl.disabled;
      var prevAria = triggerEl.getAttribute("aria-disabled");
      triggerEl.disabled = true;
      triggerEl.setAttribute("aria-disabled", "true");
      return function() {
        triggerEl.disabled = prevDisabled;
        if (prevAria === null) triggerEl.removeAttribute("aria-disabled");
        else triggerEl.setAttribute("aria-disabled", prevAria);
      };
    }
    var nodes = optimisticTargets(regionEl, op);
    var reverters = [];
    nodes.forEach(function(node) {
      if (name === "addClass" || name === "removeClass" || name === "toggleClass") {
        var had = node.classList.contains(op.value);
        if (name === "addClass") node.classList.add(op.value);
        else if (name === "removeClass") node.classList.remove(op.value);
        else node.classList.toggle(op.value);
        reverters.push(function() {
          if (had) node.classList.add(op.value);
          else node.classList.remove(op.value);
        });
      } else if (name === "setText") {
        var prevText = node.textContent;
        if (op.expr === "+1" || op.expr === "-1") {
          var parsed = parseFloat(node.textContent);
          if (!isNaN(parsed)) node.textContent = String(parsed + (op.expr === "+1" ? 1 : -1));
        } else if (typeof op.value === "string") {
          node.textContent = op.value;
        } else {
          return;  // nothing to do; do NOT paint the literal "undefined"
        }
        reverters.push(function() { node.textContent = prevText; });
      } else if (name === "setAttr") {
        var hadAttr = node.hasAttribute(op.name);
        var prevVal = node.getAttribute(op.name);
        node.setAttribute(op.name, op.value);
        reverters.push(function() {
          if (hadAttr) node.setAttribute(op.name, prevVal);
          else node.removeAttribute(op.name);
        });
      } else if (name === "removeAttr") {
        var hadRemoved = node.hasAttribute(op.name);
        var prevRemoved = node.getAttribute(op.name);
        node.removeAttribute(op.name);
        reverters.push(function() {
          if (hadRemoved) node.setAttribute(op.name, prevRemoved);
        });
      }
    });
    return function() { reverters.forEach(function(fn) { fn(); }); };
  }

  function optimisticReadProps(el) {
    var raw = el.getAttribute("data-island-props");
    if (!raw) return null;
    try { return JSON.parse(raw); } catch (err) { return null; }
  }

  function optimisticArm(triggerEl, requestKey) {
    if (triggerEl.getAttribute("data-island-primitive") !== "optimistic_apply") return;
    if (optimisticInflight.has(requestKey)) return;
    var props = optimisticReadProps(triggerEl);
    if (!props) return;
    var ops = props.ops;
    if (!Array.isArray(ops) || ops.length === 0) return;
    var regionEl = props.region ? document.querySelector(props.region) : triggerEl;
    if (!regionEl) return;
    var pendingClass = props.pendingClass || "is-optimistic-pending";
    var errorClass = props.errorClass || "is-optimistic-error";
    var info = {
      name: triggerEl.getAttribute("data-island") || "optimistic_apply",
      id: triggerEl.id || null,
      version: triggerEl.getAttribute("data-island-version") || "1"
    };

    var entry = optimisticRegions.get(regionEl);
    if (!entry) {
      // First in-flight op for this region: capture the TRUE pre-mutation
      // baseline. Re-triggers coalesce onto this entry so revert always
      // returns to the original pre-mutation state.
      entry = {
        reverters: [],
        outerHTML: regionEl.outerHTML,
        inflight: new Set(),
        swapLanded: false,
        confirmed: false,
        pendingClass: pendingClass,
        errorClass: errorClass,
        info: info
      };
      optimisticRegions.set(regionEl, entry);
      regionEl.classList.remove(errorClass);
    }
    entry.inflight.add(requestKey);
    optimisticInflight.set(requestKey, { regionEl: regionEl });

    ops.forEach(function(op) {
      if (!op || typeof op.op !== "string") return;
      if (OPTIMISTIC_ALLOWED.indexOf(op.op) === -1) {
        emit(ERROR_EVENT, { name: info.name, id: info.id, version: info.version, error: "unknown_op", reason: op.op });
        return;
      }
      try {
        var rev = optimisticApplyOp(regionEl, triggerEl, op);
        if (typeof rev === "function") entry.reverters.push(rev);
      } catch (err) {
        emit(ERROR_EVENT, { name: info.name, id: info.id, version: info.version, error: "optimistic_apply", reason: String(err && err.message || err) });
      }
    });
    regionEl.classList.add(pendingClass);
    emitAction(info, "apply", "optimistic", {});
  }

  function optimisticConfirm(requestKey) {
    // htmx:afterSwap fires ONLY when htmx actually swapped (a 2xx, or an error
    // response the app explicitly opted into swapping). It is the authoritative
    // signal that the server fragment landed — NOT htmx:beforeSwap, which also
    // fires for non-swapping error responses.
    var record = optimisticInflight.get(requestKey);
    if (!record) return;
    var entry = optimisticRegions.get(record.regionEl);
    if (!entry) return;
    entry.swapLanded = true;
    if (entry.confirmed) return;
    entry.confirmed = true;
    emitAction({ name: entry.info.name, id: entry.info.id, version: entry.info.version }, "confirm", "confirmed", {});
  }

  function optimisticSettle(requestKey, httpStatus) {
    var record = optimisticInflight.get(requestKey);
    if (!record) return;             // idempotent: already settled
    optimisticInflight.delete(requestKey);
    var regionEl = record.regionEl;
    var entry = optimisticRegions.get(regionEl);
    if (!entry) return;
    entry.inflight.delete(requestKey);
    if (entry.inflight.size > 0) return;  // wait for the last in-flight request
    regionEl.classList.remove(entry.pendingClass);
    var payload = { name: entry.info.name, id: entry.info.id, version: entry.info.version };
    if (!entry.swapLanded) {
      // No authoritative fragment landed (network/send error, timeout, or a
      // non-swapping 4xx/5xx): revert to the client's OWN pre-mutation
      // snapshot.
      try {
        for (var i = entry.reverters.length - 1; i >= 0; i--) entry.reverters[i]();
      } catch (err) {
        try {
          var tpl = document.createElement("template");
          tpl.innerHTML = entry.outerHTML;
          if (tpl.content.firstElementChild && regionEl.parentNode) {
            regionEl.parentNode.replaceChild(tpl.content.firstElementChild, regionEl);
          }
        } catch (fallbackErr) { /* leave the DOM as-is */ }
        emit(ERROR_EVENT, { name: payload.name, id: payload.id, version: payload.version, error: "revert_fallback", reason: String(err && err.message || err) });
      }
      regionEl.classList.add(entry.errorClass);
      emitAction(payload, "revert", "reverted", { httpStatus: httpStatus });
    }
    optimisticRegions.delete(regionEl);
  }

  // Registered so the islands runtime mounts the primitive for lifecycle
  // parity; arming/confirm/revert live entirely in the document-level listeners
  // below (which read props fresh), so they never depend on this mount state.
  register("optimistic_apply", { mount: function() {} });

  function optimisticDetail(evt) { return (evt && evt.detail) || {}; }
  function optimisticContext(detail) { return detail.ctx || detail; }
  function optimisticRequestKey(detail) {
    var ctx = optimisticContext(detail);
    return detail.xhr || ctx.request || ctx;
  }
  function optimisticStatus(detail) {
    var ctx = optimisticContext(detail);
    return (ctx.response && ctx.response.status) || (detail.xhr && detail.xhr.status);
  }
  onHtmxLifecycle(["htmx:beforeRequest", "htmx:before:request"], function(evt) {
    var detail = optimisticDetail(evt);
    var ctx = optimisticContext(detail);
    var el = ctx.sourceElement || detail.elt || evt.target;
    var key = optimisticRequestKey(detail);
    if (el instanceof Element && key) optimisticArm(el, key);
  });
  onHtmxLifecycle(["htmx:afterSwap", "htmx:after:swap"], function(evt) {
    var detail = optimisticDetail(evt);
    optimisticConfirm(optimisticRequestKey(detail));
  });
  onHtmxLifecycle(["htmx:afterRequest", "htmx:after:request"], function(evt) {
    var detail = optimisticDetail(evt);
    optimisticSettle(optimisticRequestKey(detail), optimisticStatus(detail));
  });
  onHtmxLifecycle(["htmx:sendError", "htmx:timeout", "htmx:error"], function(evt) {
    var detail = optimisticDetail(evt);
    optimisticSettle(optimisticRequestKey(detail), optimisticStatus(detail));
  });
  // <<< optimistic_apply adapter
"""


def islands_snippet(version: str, *, nonce: str = "") -> str:
    """Return runtime bootstrap script for island lifecycle events.

    When *nonce* is non-empty the ``<script>`` carries a ``nonce="..."``
    attribute so it survives a nonce-based CSP that no longer ships
    ``'unsafe-inline'``.
    """
    nonce_attr = f' nonce="{nonce}"' if nonce else ""
    optimistic_adapter = _OPTIMISTIC_ADAPTER_JS
    runtime = f"""
<script data-chirp="islands"{nonce_attr}>
(function() {{
  if (window.__chirpIslands) return;
  const mounts = new WeakMap();
  const cleanupByMount = new WeakMap();
  const adapters = new Map();
  const adapterLoads = new Map();
  const VERSION = "{version}";
  const STATE_EVENT = "chirp:island:state";
  const ACTION_EVENT = "chirp:island:action";
  const ERROR_EVENT = "chirp:island:error";

  function emit(eventName, payload) {{
    const detail = payload || {{}};
    document.dispatchEvent(new CustomEvent(eventName, {{ detail }}));
    window.dispatchEvent(new CustomEvent(eventName, {{ detail }}));
  }}

  function emitState(payload, state) {{
    emit(STATE_EVENT, {{
      name: payload.name,
      id: payload.id,
      version: payload.version,
      state: state,
    }});
  }}

  function emitAction(payload, action, status, extra) {{
    const detail = {{
      name: payload.name,
      id: payload.id,
      version: payload.version,
      action: action,
      status: status,
    }};
    if (extra && typeof extra === "object") {{
      Object.keys(extra).forEach((key) => {{
        detail[key] = extra[key];
      }});
    }}
    emit(ACTION_EVENT, detail);
  }}

  function onHtmxLifecycle(names, handler) {{
    const seen = typeof WeakSet !== "undefined" ? new WeakSet() : null;
    names.forEach(function(name) {{
      document.addEventListener(name, function(event) {{
        const detail = (event && event.detail) || {{}};
        const token = detail.ctx || detail;
        if (seen && token && typeof token === "object") {{
          if (seen.has(token)) return;
          seen.add(token);
        }}
        handler(event);
      }});
    }});
  }}

  function parseProps(el) {{
    const raw = el.getAttribute("data-island-props");
    if (!raw) return {{ ok: true, value: null }};
    try {{
      return {{ ok: true, value: JSON.parse(raw) }};
    }} catch (err) {{
      return {{ ok: false, value: null, error: String(err && err.message || err) }};
    }}
  }}

  function payloadFor(el) {{
    const name = el.getAttribute("data-island");
    if (!name) return null;
    const versionAttr = el.getAttribute("data-island-version") || "1";
    const src = el.getAttribute("data-island-src");
    const parsed = parseProps(el);
    const base = {{
      name,
      id: el.id || null,
      version: versionAttr,
      src: src,
      props: parsed.value,
      element: el,
    }};

    if (name.trim().length === 0) {{
      return {{ ...base, error: "missing_name", reason: "empty data-island value" }};
    }}
    if (src && /^javascript:/i.test(src)) {{
      return {{ ...base, error: "unsafe_src", reason: "data-island-src must not use javascript:" }};
    }}
    if (!parsed.ok) {{
      return {{ ...base, error: "props_parse", reason: parsed.error || "invalid props JSON" }};
    }}
    if (versionAttr !== VERSION) {{
      return {{
        ...base,
        warning: "version_mismatch",
        reason: `mount version ${{versionAttr}} differs from runtime ${{VERSION}}`,
      }};
    }}

    return {{
      ...base,
    }};
  }}

  function adapterApi(payload) {{
    return {{
      emitState: function(state) {{ emitState(payload, state); }},
      emitAction: function(action, status, extra) {{
        emitAction(payload, action, status, extra);
      }},
      emitError: function(reason, extra) {{
        const detail = {{
          ...payload,
          error: "adapter_error",
          reason: reason || "adapter error",
        }};
        if (extra && typeof extra === "object") {{
          Object.keys(extra).forEach((key) => {{
            detail[key] = extra[key];
          }});
        }}
        emit(ERROR_EVENT, detail);
      }},
    }};
  }}

  function normalizeAdapter(mod) {{
    if (!mod) return null;
    if (typeof mod.mount === "function" || typeof mod.unmount === "function") {{
      return mod;
    }}
    if (mod.default && (typeof mod.default.mount === "function" || typeof mod.default.unmount === "function")) {{
      return mod.default;
    }}
    return null;
  }}

  function register(name, adapter) {{
    if (!name || !adapter) return;
    adapters.set(name, adapter);
  }}

  async function ensureAdapter(payload) {{
    const existing = adapters.get(payload.name);
    if (existing) return existing;
    if (!payload.src) return null;

    const loadKey = payload.name + "::" + payload.src;
    if (!adapterLoads.has(loadKey)) {{
      adapterLoads.set(
        loadKey,
        import(payload.src)
          .then((mod) => {{
            const adapter = normalizeAdapter(mod) || adapters.get(payload.name);
            if (adapter) {{
              adapters.set(payload.name, adapter);
            }}
            return adapter;
          }})
          .catch((err) => {{
            emit(ERROR_EVENT, {{
              ...payload,
              error: "adapter_load",
              reason: String(err && err.message || err),
            }});
            return null;
          }})
      );
    }}
    return adapterLoads.get(loadKey);
  }}

  async function mount(el) {{
    if (!(el instanceof Element)) return;
    if (mounts.has(el)) return;
    const payload = payloadFor(el);
    if (!payload) return;
    if (payload.error) {{
      el.setAttribute("data-island-state", "error");
      emit(ERROR_EVENT, payload);
      return;
    }}
    if (payload.warning) {{
      emit(ERROR_EVENT, payload);
    }}
    mounts.set(el, payload);
    el.setAttribute("data-island-state", "mounted");
    emit("chirp:island:mount", payload);

    const adapter = await ensureAdapter(payload);
    if (!adapter || typeof adapter.mount !== "function") {{
      return;
    }}

    try {{
      const cleanup = adapter.mount(payload, adapterApi(payload));
      if (typeof cleanup === "function") {{
        cleanupByMount.set(el, cleanup);
      }}
    }} catch (err) {{
      el.setAttribute("data-island-state", "error");
      emit(ERROR_EVENT, {{
        ...payload,
        error: "adapter_mount",
        reason: String(err && err.message || err),
      }});
    }}
  }}

  function unmount(el) {{
    if (!(el instanceof Element)) return;
    if (!mounts.has(el)) return;
    const payload = mounts.get(el);
    mounts.delete(el);

    const cleanup = cleanupByMount.get(el);
    if (cleanup) {{
      cleanupByMount.delete(el);
      try {{
        cleanup();
      }} catch (err) {{
        emit(ERROR_EVENT, {{
          ...payload,
          error: "adapter_cleanup",
          reason: String(err && err.message || err),
        }});
      }}
    }}

    const adapter = adapters.get(payload.name);
    if (adapter && typeof adapter.unmount === "function") {{
      try {{
        adapter.unmount(payload, adapterApi(payload));
      }} catch (err) {{
        emit(ERROR_EVENT, {{
          ...payload,
          error: "adapter_unmount",
          reason: String(err && err.message || err),
        }});
      }}
    }}

    el.setAttribute("data-island-state", "unmounted");
    emit("chirp:island:unmount", payload);
  }}

  async function remount(el) {{
    if (!(el instanceof Element)) return;
    if (mounts.has(el)) {{
      unmount(el);
    }}
    await mount(el);
    const payload = mounts.get(el);
    if (payload) {{
      emit("chirp:island:remount", payload);
    }}
  }}

  async function scan(root) {{
    const scope = root instanceof Element || root instanceof Document ? root : document;
    const found = [];
    if (scope instanceof Element && scope.matches("[data-island]")) {{
      found.push(scope);
    }}
    scope.querySelectorAll("[data-island]").forEach((el) => found.push(el));
    await Promise.all(found.map((el) => mount(el)));
  }}

  function unmountWithin(root) {{
    const scope = root instanceof Element ? root : null;
    if (!scope) return;
    if (scope.matches("[data-island]")) {{
      unmount(scope);
    }}
    scope.querySelectorAll("[data-island]").forEach((el) => unmount(el));
  }}

{optimistic_adapter}
  document.addEventListener("DOMContentLoaded", function() {{
    void scan(document);
  }});

  onHtmxLifecycle(["htmx:beforeSwap", "htmx:before:swap"], function(event) {{
    const detail = (event && event.detail) || {{}};
    const ctx = detail.ctx || detail;
    const target = ctx.target || event.target;
    if (target instanceof Element) {{
      unmountWithin(target);
    }}
  }});

  onHtmxLifecycle(["htmx:afterSwap", "htmx:after:swap"], function(event) {{
    const detail = (event && event.detail) || {{}};
    const ctx = detail.ctx || detail;
    const target = ctx.target || event.target;
    if (target instanceof Element) {{
      void scan(target);
    }} else {{
      void scan(document);
    }}
  }});

  const channels = {{
    state: STATE_EVENT,
    action: ACTION_EVENT,
    error: ERROR_EVENT,
  }};

  window.chirpIslands = {{
    version: VERSION,
    channels: channels,
    register: register,
    scan: scan,
    mount: mount,
    unmount: unmount,
    remount: remount,
    emitState: emitState,
    emitAction: emitAction,
  }};
  window.__chirpIslands = true;
  emit("chirp:islands:ready", {{ version: VERSION }});
}})();
</script>"""
    return runtime.strip()
