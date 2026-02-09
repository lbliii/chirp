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

Optionally configure htmx response handling:

```javascript
htmx.config.responseHandling = [
    {code: "204", swap: false},
    {code: "[23]..", swap: true},
    {code: "422", swap: true},       // validation errors
    {code: "[45]..", swap: false, error: true},
];
```

Listen for the `chirpError` event for custom behavior:

```javascript
document.body.addEventListener("chirpError", (event) => {
    // Show a toast, play a sound, etc.
    console.error("Chirp error occurred");
});
```

## SSE Error Events

When an SSE event generator raises an exception:

1. The exception is logged to the console (`logger.exception()`)
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

## Error Logging

Chirp uses the `chirp.server` logger (stdlib `logging`). When running under pounce, this logger is automatically configured with the same level and format as pounce's logger.

| Error Type | Log Level | When |
|-----------|-----------|------|
| 500 (unhandled exception) | `ERROR` | Always — includes full traceback |
| 4xx (HTTP errors) | `DEBUG` | Visible when `log_level=debug` |
| Streaming error | `ERROR` | Mid-stream exception in chunked response |
| SSE generator error | `ERROR` | Exception in SSE event generator |

## Custom Error Handlers

Register custom error handlers for specific status codes:

```python
@app.error(404)
def not_found(request, exc):
    if request.is_fragment:
        return '<div class="error">Page not found</div>'
    return "Page not found"

@app.error(500)
async def server_error(request, exc):
    # Custom error handling (logging, alerting, etc.)
    return Response(body="Something went wrong", status=500)
```

Custom error handlers bypass the debug page and htmx headers — you control the full response.
