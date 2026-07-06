# Error Handling

Chirp provides a layered error handling system designed for developer ergonomics. Every error is logged to the console regardless of mode, and debug mode renders rich diagnostic pages in the browser.

## Debug Mode

Enable debug mode in `AppConfig`:

```python
from chirp import App
from chirp.config import AppConfig

app = App(config=AppConfig(debug=True))
```

When `debug=True` and an unhandled exception occurs:

- **Console**: Full traceback is always logged via `logger.exception()` (even when `debug=False`)
- **Browser**: A rich error page with source context, locals, request info, and template diagnostics
- **DevTools**: Full-page responses load Chirp DevTools for htmx, SSE, View Transition, render-plan, and Swap Doctor diagnostics. See `docs/devtools.md`.

When `debug=False` (production):

- **Console**: Full traceback is still logged
- **Browser**: Generic "Internal Server Error" (no implementation details exposed)

## Rich Debug Error Page

The debug page renders without depending on your template environment (kida). If the error IS in your templates, the error page still works.

### What It Shows

- **Exception type and message** at the top
- **Template error panel** (if the error is a kida template error) with source snippet, expression, values, and "did you mean?" suggestions
- **Traceback** with:
  - 5 lines of source context around each frame
  - Error line highlighted
  - Expandable local variables per frame
  - Application frames visually distinguished from framework/stdlib frames (marked with an `APP` badge)
- **Request context**: method, path, HTTP version, client address, headers (sensitive values masked), query parameters, path parameters
- **Environment**: Python version, chirp version

### Fragment Mode

For htmx fragment requests (`HX-Request: true`), the debug page renders as a compact `<div>` instead of a full HTML document. It fits into the existing page layout where the fragment would have appeared.

## DevTools For Hypermedia Debugging

Debug mode also injects Chirp DevTools into full-page responses. Open the app in
a browser, press `Ctrl+Shift+D`, and inspect htmx activity, effective `hx-*`
inheritance, render-plan headers, native Chirp EventStream traces, View
Transitions, DOM diffs, and Swap Doctor warnings.

For agent-readable diagnostics, browser-capable agents can evaluate:

```javascript
window.ChirpHtmxDebug.help()
window.ChirpHtmxDebug.exportRecordsJson()
```

Use this before guessing from screenshots when debugging htmx swaps, OOB
regions, Suspense blocks, SSE, or fragment targets.

## Editor Integration

Set the `CHIRP_EDITOR` environment variable to make stack frame file paths clickable in the debug page.

### Presets

```bash
# VS Code
export CHIRP_EDITOR=vscode

# Cursor
export CHIRP_EDITOR=cursor

# Sublime Text
export CHIRP_EDITOR=sublime

# TextMate
export CHIRP_EDITOR=textmate

# IntelliJ IDEA
export CHIRP_EDITOR=idea

# PyCharm
export CHIRP_EDITOR=pycharm
```

### Custom Pattern

Use `__FILE__` and `__LINE__` placeholders:

```bash
export CHIRP_EDITOR="myeditor://open?file=__FILE__&line=__LINE__"
```

## htmx Error Handling

When chirp returns an error response to an htmx fragment request, it includes headers that help the client handle errors gracefully:

| Header | Value | Purpose |
|--------|-------|---------|
| `HX-Retarget` | `#chirp-error` | Redirect error content to a dedicated container |
| `HX-Reswap` | `innerHTML` | Replace (not append) the error content |
| `HX-Trigger` | `chirpError` | Fire a client-side event for custom handling |

### Recommended Setup

Add an error container to your base layout:

```html
<div id="chirp-error"></div>
```

With htmx 2, optionally configure response handling:

```javascript
htmx.config.responseHandling = [
    {code: "204", swap: false},
    {code: "[23]..", swap: true},
    {code: "422", swap: true},       // validation errors
    {code: "[45]..", swap: false, error: true},
];
```

The exact htmx 4 preview configures this policy for you: bounded 4xx HTML,
including `ValidationError` 422 fragments, swaps into the requested target;
5xx HTML does not swap by default, so an unhandled failure cannot replace a
broad shell. Opt a 5xx into swapping only with a statically present local
`hx-status:5xx` target. `app.check()` rejects broad or unresolved 5xx targets.

Listen for the `chirpError` event for custom behavior:

```javascript
document.body.addEventListener("chirpError", (event) => {
    // Show a toast, play a sound, etc.
    console.error("Chirp error occurred");
});
```

## SSE Error Boundaries

Chirp uses two levels of error isolation so that a single rendering failure doesn't kill the entire SSE stream.

### Per-Event Boundary

If a single `Fragment` fails to render (e.g., a variable is `None`, a block has a template error), chirp catches the exception **per-event**:

- **Production**: the failed event is silently skipped; the stream continues delivering other blocks
- **Debug**: an error event is sent targeting the specific block, replacing it with a `<div class="chirp-block-error">` that shows the exception type and message inline

Other blocks on the same page keep updating normally — only the broken block is affected.

### Context Builder Boundary

In reactive streams (`reactive_stream()`), the `context_builder()` function runs before rendering any blocks for a given change event. If it raises (e.g., the document was deleted mid-render), the entire event is skipped and the stream waits for the next change. The failure is logged with a full traceback.

### Catastrophic Errors

If something truly unexpected happens (ASGI transport failure, unrecoverable state), the outer error handler still kicks in:

1. The exception is logged to the console
2. An `event: error` SSE event is sent to the client
3. The stream is closed

In **debug mode**, the error event includes the full traceback. In **production**, it contains a generic "Internal server error" message.

### Client-Side Handling

```javascript
const source = new EventSource("/events");

source.addEventListener("error", (event) => {
    if (event.data) {
        console.error("SSE error:", event.data);
    }
});
```

### Styling Block Errors (Debug Mode)

In debug mode, failed blocks are replaced with `<div class="chirp-block-error">`. Style them in your app's CSS:

```css
.chirp-block-error {
    background: #fef2f2;
    border: 1px solid #fca5a5;
    border-radius: 4px;
    padding: 0.5rem;
    font-family: monospace;
    font-size: 0.85rem;
    color: #991b1b;
}
```

## Error Logging

Chirp uses the `chirp.server` logger (stdlib `logging`). When running under pounce, this logger is automatically configured with the same level and format as pounce's logger.

| Error Type | Log Level | Logger | When |
|-----------|-----------|--------|------|
| 500 (unhandled exception) | `ERROR` | `chirp.server` | Always — includes full traceback |
| 4xx (HTTP errors) | `DEBUG` | `chirp.server` | Visible when `log_level=debug` |
| Streaming error | `ERROR` | `chirp.server` | Mid-stream exception in chunked response |
| SSE per-event render error | `ERROR` | `chirp.server` | Fragment fails to render; stream continues |
| SSE context builder error | `ERROR` | `chirp.reactive` | `context_builder()` raises; event skipped |
| SSE catastrophic error | `ERROR` | `chirp.server` | Unrecoverable error; stream terminates |

## Custom Error Handlers

Register custom error handlers for specific status codes:

```python
@app.error(404)
def not_found(request, exc):
    if request.is_htmx:
        return '<div class="error">Page not found</div>'
    return "Page not found"

@app.error(500)
async def server_error(request, exc):
    # Custom error handling (logging, alerting, etc.)
    return Response(body="Something went wrong", status=500)
```

Custom error handlers bypass the debug page and htmx headers — you control the full response.
