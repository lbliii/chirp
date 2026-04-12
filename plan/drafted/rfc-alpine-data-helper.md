# RFC: `alpine_json_config` Template Global

**Status**: Implemented (Chirp `alpine_json_config` + docs/tests)  
**Date**: 2026-04-11  
**Scope**: `src/chirp/server/alpine.py`, `src/chirp/app/compiler.py`  
**Related**: RFC: `tojson` Attribute-Safe Mode (Kida), Alpine.js injection (`src/chirp/middleware/inject.py`)

---

## Problem

Every interactive Chirp page that uses Alpine.js with server-provided configuration needs the same boilerplate:

```kida
<script id="game-config" type="application/json">{{ game_config | tojson }}</script>
<div x-data="matchGame()">
  ...
</div>
<script>
document.addEventListener("alpine:init", function() {
  var config = JSON.parse(document.getElementById("game-config").textContent);
  Alpine.data("matchGame", function() {
    return {
      rows: config.rows,
      cols: config.cols,
      // ... rest of component
    };
  });
});
</script>
```

The `<script type="application/json">` bridge is the recommended pattern (documented in Chirp's Alpine guide, Kida's CLAUDE.md, and the kida-chirp-integration skill) because:

1. `tojson` in HTML attributes breaks double-quoted delimiters (see Kida RFC: tojson attr-safe)
2. It avoids CSP issues with inline JSON evaluation
3. It is the Django community's established pattern (`json_script`)

But the `<script>` tag itself is easy to get wrong:

- **Missing `type="application/json"`** — browser executes as JS, throws SyntaxError
- **ID collision** — multiple components on the same page reuse an ID
- **Forgetting `tojson`** — raw Python dict output instead of JSON
- **XSS via unescaped values** — though `tojson` wraps in `Markup()`, manual construction of the tag can skip escaping

### Evidence

During the b-site matching game build, the Alpine component required three debugging iterations:

1. First attempt: `x-data="matchGame({{ config | tojson }})"` — broken HTML attributes
2. Second attempt: `{% block page_scripts %}` with the JSON tag — block silently dropped (composition model)
3. Third attempt: inline `<script type="application/json">` inside `page_content` — correct

The final working pattern took ~15 lines of template boilerplate for a 3-line semantic intent: "pass this Python dict to this Alpine component."

---

## Goals

1. Provide a one-call template helper that safely emits a `<script type="application/json">` tag.
2. Keep it minimal — only handle the JSON-to-DOM bridge, not the Alpine component registration.
3. Register automatically when `alpine=True` (Chirp is the Alpine authority).

### Non-Goals

- Generating `Alpine.data()` registration code — that's app-specific JavaScript.
- Generating the `alpine:init` listener — the `safeData` helper already handles registration timing.
- Replacing the `<script type="application/json">` pattern entirely — it's the correct approach, we're just removing the boilerplate.

---

## Design

### Template Global: `alpine_json_config`

```python
def alpine_json_config(id: str, data: Any) -> Markup:
    """Emit a <script type="application/json"> tag for Alpine component config.

    Provides a safe bridge for passing server-side data to client-side Alpine
    components without HTML attribute quoting issues.

    Args:
        id: DOM id for the script tag. Used by the Alpine component to locate
            and parse the config via ``document.getElementById(id).textContent``.
        data: Python value to serialize as JSON. Uses ``json.dumps`` with
            ``default=str`` for non-JSON-serializable types.

    Returns:
        Markup: Safe HTML string containing the script tag.

    Usage in templates::

        {{ alpine_json_config("game-config", game_config) }}
        <div x-data="matchGame()">...</div>
        <script>
        document.addEventListener("alpine:init", function() {
          var cfg = JSON.parse(document.getElementById("game-config").textContent);
          Alpine.data("matchGame", function() { return { ...cfg }; });
        });
        </script>
    """
    json_str = json.dumps(data, default=str)
    escaped_id = _html_escape_attr(id)
    return Markup(
        f'<script id="{escaped_id}" type="application/json">{json_str}</script>'
    )
```

### Escaping Strategy

- **`id` parameter**: HTML-attribute-escaped to prevent injection via dynamic IDs. Uses `_html_escape_attr` (replace `&`, `"`, `<`, `>`).
- **`data` parameter**: Serialized via `json.dumps(data, default=str)`. The output is placed inside a `<script type="application/json">` tag. Browsers do not parse the content of `type="application/json"` scripts as HTML, so HTML entity encoding is unnecessary. However, we must ensure the JSON does not contain `</script>` which would prematurely close the tag. `json.dumps` naturally escapes `/` as `\/` when `ensure_ascii=True`, but Python's default is `ensure_ascii=False`. We should add a safety replacement: `json_str.replace("</", "<\\/")`.

Updated implementation:

```python
def alpine_json_config(id: str, data: Any) -> Markup:
    json_str = json.dumps(data, default=str)
    json_str = json_str.replace("</", "<\\/")
    escaped_id = id.replace("&", "&amp;").replace('"', "&quot;")
    return Markup(
        f'<script id="{escaped_id}" type="application/json">{json_str}</script>'
    )
```

### Registration

Register as a template global when `alpine=True` in `src/chirp/app/compiler.py`:

```python
# In _build_middleware (after Alpine injection setup):
if config.alpine:
    from chirp.server.alpine import alpine_snippet, alpine_json_config

    middleware_list.append(
        AlpineInject(
            alpine_snippet(config.alpine_version, config.alpine_csp),
            full_page_only=True,
        )
    )
    # Register Alpine template helpers
    template_globals["alpine_json_config"] = alpine_json_config
```

The global is only available when Alpine is enabled — it makes no sense without the Alpine runtime.

### File Location

Add `alpine_json_config` to `src/chirp/server/alpine.py` alongside the existing `alpine_snippet` function. This keeps all Alpine-related utilities in one module.

---

## Usage Examples

### Simple Component

```kida
{{ alpine_json_config("game-config", game_config) }}
<div x-data="matchGame()">
  <template x-for="card in cards">
    <div class="card" @click="flip(card)">{{ card.emoji }}</div>
  </template>
</div>
<script>
document.addEventListener("alpine:init", function() {
  var cfg = JSON.parse(document.getElementById("game-config").textContent);
  Alpine.data("matchGame", function() {
    return {
      cards: cfg.card_types,
      flip: function(card) { /* ... */ },
    };
  });
});
</script>
```

**Before** (without helper): 4 lines of template boilerplate for the JSON tag.
**After**: 1 line.

### Multiple Components on One Page

```kida
{{ alpine_json_config("chart-data", chart_data) }}
{{ alpine_json_config("filter-config", filter_options) }}

<div x-data="chart()">...</div>
<div x-data="filterBar()">...</div>
```

Each component gets its own config tag with a unique ID.

### With `safeData` (htmx-safe)

```kida
{{ alpine_json_config("editor-cfg", editor_config) }}
<div x-data="editor()">...</div>
<script>
(function() {
  var cfg = JSON.parse(document.getElementById("editor-cfg").textContent);
  window._chirpAlpineData("editor", function() {
    return { ...cfg, init: function() { /* ... */ } };
  });
})();
</script>
```

Using `_chirpAlpineData` (Chirp's pre-Alpine queue) instead of `alpine:init` ensures the component registers correctly even if the script runs before Alpine loads.

---

## What This Intentionally Does NOT Do

1. **No `Alpine.data()` generation** — The component body is arbitrary JavaScript with closures, methods, watchers, and lifecycle hooks. Generating it from a template would require a JS-in-template DSL, which is too opinionated and unmaintainable.

2. **No automatic wiring** — A `{% call alpine_component("name", data) %}...{% end %}` macro was considered and rejected. It would need to:
   - Generate a unique ID for the JSON tag
   - Emit the `<script type="application/json">` tag
   - Emit the `alpine:init` listener with the component registration
   - Somehow accept the component's JavaScript body as slot content

   This couples template structure to JavaScript evaluation timing and makes debugging harder — you can't inspect the generated script tag independently.

3. **No CSP nonce injection** — When `alpine_csp=True`, inline scripts need nonces. That's a separate concern handled by the `AlpineInject` middleware. The JSON config tag does not execute code, so it needs no nonce.

---

## Testing Strategy

1. **Basic output**: `alpine_json_config("my-id", {"key": "value"})` produces `<script id="my-id" type="application/json">{"key": "value"}</script>`.
2. **ID escaping**: `alpine_json_config('a"b', {})` produces `id="a&quot;b"`.
3. **Script tag safety**: Data containing `</script>` is escaped to `<\/script>`.
4. **Non-serializable values**: `default=str` handles dates, paths, etc.
5. **Markup type**: Output is `Markup` (not double-escaped by autoescaper).
6. **Not registered without Alpine**: When `alpine=False`, `alpine_json_config` is not in template globals.
7. **Integration test**: A Chirp app with `alpine=True` can use `{{ alpine_json_config(...) }}` in a template and the output appears in the rendered HTML.

---

## Implementation Plan

1. Add `alpine_json_config` function to `src/chirp/server/alpine.py`.
2. Register it as a template global in `src/chirp/app/compiler.py` when `alpine=True`.
3. Add unit tests to `tests/test_alpine.py`.
4. Update `site/content/docs/guides/alpine.md` with the helper usage.
5. Update chirp-ui CLAUDE.md to recommend the helper.

Estimated effort: 1-2 hours including tests and docs.

---

## Future Considerations

1. **`alpine_json_config` + `tojson(attr=true)`**: Both solve the same root problem (JSON in HTML) from different angles. They are complementary — `alpine_json_config` for the `<script>` tag pattern, `tojson(attr=true)` for inline attribute usage. Docs should cross-reference both.

2. **Django-style `json_script` filter**: If `alpine_json_config` proves popular, Kida could add a general `json_script` filter: `{{ data | json_script("my-id") }}` that emits the same `<script>` tag. This would be framework-agnostic (not Alpine-specific). But that's a Kida decision, not a Chirp one.

3. **Chirp DevTools integration**: The Alpine guide could recommend a development-mode overlay that shows which JSON config tags are present and which Alpine components consumed them, aiding debugging.
