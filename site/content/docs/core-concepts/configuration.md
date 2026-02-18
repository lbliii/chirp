---
title: Configuration
description: AppConfig frozen dataclass and all configuration options
draft: false
weight: 30
lang: en
type: doc
tags: [configuration, appconfig, settings]
keywords: [config, appconfig, settings, debug, host, port, secret-key, template-dir]
category: explanation
---

## AppConfig

Chirp uses a frozen dataclass for configuration. Every field has IDE autocomplete, type checking, and no runtime `KeyError` surprises.

```python
from chirp import App, AppConfig

config = AppConfig(
    debug=True,
    host="0.0.0.0",
    port=8000,
    secret_key="change-me-in-production",
    template_dir="templates/",
)

app = App(config=config)
```

`AppConfig` is `@dataclass(frozen=True, slots=True)`. Once created, it cannot be mutated. This is intentional -- config should not change after the app starts.

## Configuration Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `debug` | `bool` | `False` | Enable debug mode (verbose errors, template auto-reload) |
| `host` | `str` | `"127.0.0.1"` | Bind address for the development server |
| `port` | `int` | `8000` | Bind port for the development server |
| `secret_key` | `str \| None` | `None` | Secret key for session signing (required for sessions) |
| `template_dir` | `str` | `"templates"` | Directory for kida templates |
| `static_dir` | `str \| None` | `None` | Directory for static files (if using StaticFiles middleware) |
| `static_url` | `str` | `"/static"` | URL prefix for static files |
| `safe_target` | `bool` | `True` | Auto-add `hx-target="this"` to event-driven elements |
| `sse_lifecycle` | `bool` | `True` | Inject SSE connection status (`data-sse-state`) and custom events |
| `view_transitions` | `bool` | `False` | Auto-inject View Transitions API meta tag, CSS defaults, and htmx config |
| `alpine` | `bool` | `False` | Enable Alpine.js script injection for local UI state |
| `alpine_version` | `str` | `"3.15.8"` | Pinned Alpine version (unpkg CDN) |
| `alpine_csp` | `bool` | `False` | Use CSP-safe Alpine build for strict Content-Security-Policy |
| `islands` | `bool` | `False` | Inject framework-agnostic islands runtime lifecycle hooks |
| `islands_version` | `str` | `"1"` | Version tag exposed in `data-island-version` and runtime events |
| `islands_contract_strict` | `bool` | `False` | Warn on missing stable island mount IDs during `app.check()` |
| `sse_heartbeat_interval` | `float` | `15.0` | Seconds between SSE heartbeat comments |
| `sse_retry_ms` | `int \| None` | `None` | SSE reconnection interval sent to client |
| `max_content_length` | `int` | `16777216` | Maximum request body size in bytes (16 MB) |

## Debug Mode

When `debug=True`:

- Detailed error pages with tracebacks are shown in the browser
- Templates auto-reload when modified (no server restart needed)
- Stricter validation warnings are surfaced

```python
config = AppConfig(debug=True)
```

:::{warning}
Never enable debug mode in production. It exposes internal details including source code and tracebacks.
:::

## Secret Key

Required for session middleware and CSRF protection. Use a strong random value in production:

```python
import secrets

config = AppConfig(
    secret_key=secrets.token_hex(32),
)
```

:::{note}
If you use `SessionMiddleware` or `CSRFMiddleware` without setting a `secret_key`, Chirp raises a `ConfigurationError` at startup.
:::

## Default Configuration

If you don't pass a config, sensible defaults are used:

```python
app = App()  # Uses default AppConfig
```

This is equivalent to:

```python
app = App(config=AppConfig())
```

## Next Steps

- [[docs/core-concepts/app-lifecycle|App Lifecycle]] -- How the app freezes
- [[docs/middleware/builtin|Built-in Middleware]] -- Middleware that uses config
- [[docs/reference/api|API Reference]] -- Complete API surface
