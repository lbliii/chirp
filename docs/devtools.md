# Chirp DevTools

Chirp DevTools is the debug-mode browser overlay for htmx and hypermedia
behavior. It is intentionally opt-in: enable it while developing, and keep it
off in production.

## Enable It

Use the development CLI when possible:

```bash
chirp dev app:app
```

That command forces `debug=True` for the running app. Without the CLI, configure
the app directly:

```python
from chirp import App, AppConfig

app = App(AppConfig(debug=True))
```

If an app uses `AppConfig.from_env()`, `CHIRP_DEBUG=1` enables debug mode.

## Use It

Open the app in a browser:

- `Ctrl+Shift+D` toggles the DevTools drawer.
- `Ctrl+Shift+K` toggles the inspector for effective `hx-*` settings.
- Expanded htmx request rows include Swap Doctor diagnostics for broad
  inherited targets, missing `hx-select` matches, no-op swaps, full-page
  documents returned to fragments, missing targets, and render-plan clues.

## Agent Workflow

Browser-capable agents should activate debug mode when investigating htmx,
OOB, Suspense, SSE, fragment-target, or content-negotiation bugs. After opening
the app, evaluate these commands in the browser context:

```javascript
window.ChirpHtmxDebug.help()
window.ChirpHtmxDebug.exportRecordsJson()
```

`help()` describes the available API. `exportRecordsJson()` returns htmx
requests, errors, SSE connections and events, View Transition events, render
plans, and Swap Doctor records in a machine-readable form.
