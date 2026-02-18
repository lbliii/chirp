"""Framework-agnostic islands runtime bootstrap.

Injects a lightweight browser runtime that discovers ``[data-island]`` roots,
parses serialized props, and emits lifecycle events. Frontend adapters can
listen to these events to mount/unmount framework islands.
"""


def islands_snippet(version: str) -> str:
    """Return runtime bootstrap script for island lifecycle events."""
    runtime = f"""
<script data-chirp="islands">
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
            const adapter = normalizeAdapter(mod);
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

  document.addEventListener("DOMContentLoaded", function() {{
    void scan(document);
  }});

  document.addEventListener("htmx:beforeSwap", function(event) {{
    if (event && event.target instanceof Element) {{
      unmountWithin(event.target);
    }}
  }});

  document.addEventListener("htmx:afterSwap", function(event) {{
    if (event && event.target instanceof Element) {{
      void scan(event.target);
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
