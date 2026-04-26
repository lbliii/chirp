# Mounting Apps And Plugins

Chirp has two mounting APIs with deliberately different jobs:

| API | Use For | Shape |
|-----|---------|-------|
| `app.mount(prefix, plugin)` | Reusable packaged features | Object with `register(app, prefix)` |
| `app.mount_app(prefix, sub_app)` | Temporary composition of two Chirp apps during a migration | Pre-freeze `App` |

Use `mount()` when you are installing an extension that owns its registration surface. Use
`mount_app()` when you already have a second Chirp app and need both apps on one port while a
route tree is being moved or split.

## `mount_app`

`mount_app(prefix, sub_app)` hoists a pre-freeze sub-app into the parent app. The parent receives
the sub-app's pending routes with the prefix applied, plus compatible middleware, hooks, loaders,
template globals, filters, context providers, error handlers, contract checks, and severity
overrides.

```python
from chirp import App

main = App()
console = App()

@console.route("/", name="console.home")
def console_home():
    return "Console"

main.mount_app("/console", console)

assert main.url_for("console.home") == "/console"
```

The sub-app is consumed by the mount. Calling `sub_app.freeze()` or `sub_app.run()` after
`mount_app()` raises `RuntimeError` with a message pointing back to the mount. This protects you
from accidentally serving a half-mounted app as if it were still standalone.

## Merge Rules

The parent app wins when both apps define the same template global, filter, provider, or error
handler. Dropped sub-app entries surface as `INFO` contract issues in the `mount_app_merge`
category, so the merge is visible without failing startup.

Route names are preserved. If the parent and sub-app use the same route name for different paths,
the `route_names` contract check reports an `ERROR`. Rename one side with an explicit route name
or a module-level `name = "..."` in a mounted `page.py`.

## Limits

`mount_app()` is not full ASGI composition. It does not keep a second runtime behind the prefix.
It also rejects sub-app state that v1 cannot hoist safely, including mounted page trees with deep
page-shell state and database/migration lifecycle ownership. In those cases, collapse the route
tree into the parent app or keep the sub-app deployed separately until the migration is ready.

## Contract Checks

Run `app.check()` after mounting. The relevant categories are:

| Category | Meaning |
|----------|---------|
| `route_names` | Duplicate names across different route paths |
| `mount_app_merge` | Parent-wins merge dropped a sub-app entry |
| `page_handlers` | Mounted page module is missing a recognized handler |

Use `app.override_contract_severity(...)` only when you understand the tradeoff. Duplicate route
names usually mean `url_for(...)` would become ambiguous, so fixing the names is the better path.
