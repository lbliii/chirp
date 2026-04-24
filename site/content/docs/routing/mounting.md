---
title: Mounting
description: Compose reusable plugins and full sub-apps under a URL prefix
draft: false
weight: 40
lang: en
type: doc
tags: [routing, mounting, plugins, composition]
keywords: [mount, mount_app, plugin, compose, sub-app, prefix]
category: guide
---

## Two mount APIs — `mount` vs `mount_app`

Chirp provides two ways to compose code under a URL prefix. They solve different problems:

| | `app.mount(prefix, plugin)` | `app.mount_app(prefix, sub_app)` |
|---|---|---|
| **Input** | Any object with a `register(app, prefix)` method | Another `chirp.App` |
| **When to use** | Reusable packaged piece: docs site, auth flow, admin console shipped as a library | Transitional composition: you have two full apps and need them on one port during a migration |
| **Who owns the surface** | The plugin author — `register()` decides what to expose on the host app | You — the sub-app is a Chirp app you wrote, with all the normal APIs |
| **Lifecycle** | Plugin's `register()` runs once at mount time; plugin has no independent freeze | Sub-app is **consumed**: its pending routes, middleware, and hooks are hoisted into the parent; calling `sub_app.freeze()`/`run()` afterwards raises `RuntimeError` |
| **Middleware** | Plugin typically adds via `app.add_middleware(...)` inside `register()` | Sub-app's middleware is appended to the parent's list |
| **Template globals** | Plugin registers via `app.template_global()` inside `register()` | Sub-app's globals merge into the parent with **parent-wins** semantics |
| **Collisions** | Plugin can check the parent before registering | Parent wins; dropped sub-app entries surface as INFO contract issues in category `mount_app_merge` |
| **Permanence** | Stable — plugins are designed to be mounted | Transitional — once the migration is done, collapse the sub-app into the parent |

### When to reach for which

- **Shipping a reusable piece?** Write a plugin. The `register(app, prefix)` contract is simple, and consumers don't need to know your internals.
- **Midway through a file-system / IA refactor with two apps and one deployment slot?** Use `mount_app`. One `freeze()`, one middleware stack, one `app.check()` run — no two-stack request-time composition.

## `mount(prefix, plugin)` — reusable plugins

```python
class DocsPlugin:
    def register(self, app: App, prefix: str) -> None:
        @app.route(f"{prefix}/", name="docs.home")
        async def home(request):
            return Template("docs/home.html")

        @app.route(f"{prefix}/{{page}}")
        async def page(request, page: str):
            return Template("docs/page.html", page=page)


dashboard = App(AppConfig(...))
dashboard.mount("/docs", DocsPlugin())
```

Anything the plugin registers (routes, middleware, template globals, contract checks) is persisted on the host app directly. The plugin has no independent lifecycle.

## `mount_app(prefix, sub_app)` — sub-app composition

```python
console_app = App(AppConfig(template_dir="console/templates"))

@console_app.route("/", name="console.home")
async def home(request):
    return Template("home.html")

@console_app.route("/users/{user_id}")
async def user(request, user_id: int):
    return Template("user.html", user_id=user_id)

console_app.add_middleware(ConsoleAuthMiddleware())
console_app.template_global("console_theme")(lambda: "dark")


dashboard_app = App(AppConfig(template_dir="dashboard/templates"))

@dashboard_app.route("/")
async def index(request):
    return Template("index.html")

dashboard_app.add_middleware(SessionMiddleware(...))
dashboard_app.mount_app("/console", console_app)
dashboard_app.run()
```

After `mount_app`:

- `/` → `dashboard` home
- `/console` → console home (`url_for("console.home")` returns `/console`)
- `/console/users/{user_id}` → console user detail
- For `/console/**` requests the middleware stack is: `SessionMiddleware` → `ConsoleAuthMiddleware` → handler.
- `console_theme` is available in both dashboards' and console's templates (parent-wins merge).
- `console_app.run()` now raises `RuntimeError` — it has been consumed.

### Merge rules

| Category | Rule |
|---|---|
| Routes | Paths are prefixed; duplicate paths (after prefixing) fail at `freeze()` via the router's existing duplicate check. |
| Route names | Preserved as-is; cross-app name collisions surface via the existing `route_names` contract check. |
| Middleware | Appended in sub-app order. Parent's middleware wraps sub-app's. |
| Template globals / filters / providers / error handlers / severity overrides | **Parent wins.** Dropped sub-app entries recorded as INFO issues in category `mount_app_merge`. |
| Startup / shutdown hooks (including worker hooks) | Appended (parent hooks fire first). |
| Reload dirs | Union (dedup). |
| Contract checks | Appended (order-independent by design). |

### Unsupported sub-app state

`mount_app` raises `ConfigurationError` when the sub-app carries deep page/shell state that would silently break rendering on the parent:

- `mount_pages(...)`-discovered routes, metas, templates, layout chains
- Registered sections, OOB regions, fragment targets, layout presets, live blocks
- A custom kida environment, database, or migrations directory

If you hit this, register those on the parent directly or keep the two apps deployed separately. Future versions may relax some of these — see `docs/rfcs/005-mount-app.md`.

### `mount_app` is a migration tool

Once the refactor that motivated `mount_app` is done, collapse the sub-app into the parent: move its routes, middleware, and hooks inline. Chained `mount_app` calls work, but the result is harder to reason about than one flat app.
