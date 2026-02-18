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
  const registry = new WeakMap();
  const VERSION = "{version}";

  function parseProps(el) {{
    const raw = el.getAttribute("data-island-props");
    if (!raw) return null;
    try {{
      return JSON.parse(raw);
    }} catch (_err) {{
      return null;
    }}
  }}

  function payloadFor(el) {{
    const name = el.getAttribute("data-island");
    if (!name) return null;
    return {{
      name,
      id: el.id || null,
      version: el.getAttribute("data-island-version") || "1",
      src: el.getAttribute("data-island-src"),
      props: parseProps(el),
      element: el,
    }};
  }}

  function emit(eventName, payload) {{
    const detail = payload || {{}};
    document.dispatchEvent(new CustomEvent(eventName, {{ detail }}));
    window.dispatchEvent(new CustomEvent(eventName, {{ detail }}));
  }}

  function mount(el) {{
    if (!(el instanceof Element)) return;
    if (registry.has(el)) return;
    const payload = payloadFor(el);
    if (!payload) return;
    registry.set(el, payload);
    el.setAttribute("data-island-state", "mounted");
    emit("chirp:island:mount", payload);
  }}

  function unmount(el) {{
    if (!(el instanceof Element)) return;
    if (!registry.has(el)) return;
    const payload = registry.get(el);
    registry.delete(el);
    el.setAttribute("data-island-state", "unmounted");
    emit("chirp:island:unmount", payload);
  }}

  function remount(el) {{
    if (!(el instanceof Element)) return;
    if (registry.has(el)) {{
      unmount(el);
    }}
    mount(el);
    const payload = registry.get(el);
    if (payload) {{
      emit("chirp:island:remount", payload);
    }}
  }}

  function scan(root) {{
    const scope = root instanceof Element || root instanceof Document ? root : document;
    const found = [];
    if (scope instanceof Element && scope.matches("[data-island]")) {{
      found.push(scope);
    }}
    scope.querySelectorAll("[data-island]").forEach((el) => found.push(el));
    found.forEach((el) => mount(el));
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
    scan(document);
  }});

  document.addEventListener("htmx:beforeSwap", function(event) {{
    if (event && event.target instanceof Element) {{
      unmountWithin(event.target);
    }}
  }});

  document.addEventListener("htmx:afterSwap", function(event) {{
    if (event && event.target instanceof Element) {{
      scan(event.target);
    }} else {{
      scan(document);
    }}
  }});

  window.chirpIslands = {{
    version: VERSION,
    scan: scan,
    mount: mount,
    unmount: unmount,
    remount: remount,
  }};
  window.__chirpIslands = true;
  emit("chirp:islands:ready", {{ version: VERSION }});
}})();
</script>"""
    return runtime.strip()
