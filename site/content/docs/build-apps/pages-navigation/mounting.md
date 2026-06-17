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

## What mounting is

Mounting composes code from elsewhere under a URL prefix on your app, so one running
Chirp app can serve several feature areas — a docs site at `/docs`, an admin console at
`/console`, your own pages everywhere else.

There are two tools, and they answer different questions:

- **`app.mount(prefix, plugin)`** — you are pulling in a reusable, packaged piece (a docs
  site, an auth flow, an admin console shipped as a library) that knows how to register
  itself.
- **`app.mount_app(prefix, sub_app)`** — you have two full Chirp apps and need them on one
  port during a migration. The sub-app is consumed into the parent: one freeze, one
  middleware stack, one `app.check()`.

:::{note}
New app? You probably don't need mounting. [[docs/build-apps/pages-navigation/routes|Register routes directly on one app]] instead. Reach for mounting only to pull in a packaged plugin, or to merge two apps during a migration.
:::

## Which one do I want?

:::{list-table}
:header-rows: 1

* - API
  - Input
  - Reach for it when
* - **`mount`**
  - Any object with a `register(app, prefix)` method
  - You ship or consume a reusable, packaged piece.
* - **`mount_app`**
  - Another `chirp.App`
  - You have two full apps and need them on one port, temporarily.
:::

## Minimal examples

:::{tab-set}
:::{tab-item} mount (plugin)
A plugin is any object with a `register(app, prefix)` method. Whatever it registers —
routes, middleware, template globals — is persisted on the host app directly. The plugin
has no independent lifecycle.

```python
from chirp import App, AppConfig, Request, Template

class DocsPlugin:
    def register(self, app: App, prefix: str) -> None:
        @app.route(f"{prefix}/", name="docs.home")
        async def home(request: Request):
            return Template("docs/home.html")

        @app.route(f"{prefix}/{{page}}")
        async def page(request: Request, page: str):
            return Template("docs/page.html", page=page)


dashboard = App(AppConfig(template_dir="templates"))
dashboard.mount("/docs", DocsPlugin())
```

`mount` requires the plugin to expose a callable `register`. Anything else raises
`ConfigurationError`.
:::{/tab-item}
:::{tab-item} mount_app (sub-app)
You write two full Chirp apps, then fold one into the other. The sub-app's routes are
prefixed and its middleware, hooks, and template globals are hoisted onto the parent.

`ConsoleAuthMiddleware` below stands in for your own auth middleware.

```python
from chirp import App, AppConfig, Request, Template
from chirp.middleware.sessions import SessionMiddleware

console_app = App(AppConfig(template_dir="console/templates"))

@console_app.route("/", name="console.home")
async def home(request: Request):
    return Template("home.html")

@console_app.route("/users/{user_id:int}")
async def user(request: Request, user_id: int):
    return Template("user.html", user_id=user_id)

console_app.add_middleware(ConsoleAuthMiddleware())

dashboard_app = App(AppConfig(template_dir="dashboard/templates"))

@dashboard_app.route("/")
async def index(request: Request):
    return Template("index.html")

dashboard_app.add_middleware(SessionMiddleware(secret_key="..."))
dashboard_app.mount_app("/console", console_app)
dashboard_app.run()
```

After `mount_app("/console", console_app)`:

- `/` serves the dashboard home.
- `/console` serves the console home (`url_for("console.home")` returns `/console`).
- `/console/users/{user_id:int}` serves the console user detail.
- For `/console/**` requests the middleware stack is `SessionMiddleware` →
  `ConsoleAuthMiddleware` → handler (parent middleware wraps the sub-app's).
:::{/tab-item}
:::{/tab-set}

:::{warning}
After `mount_app`, the sub-app is **consumed**. Calling `console_app.freeze()` or
`console_app.run()` raises `RuntimeError` — serve it through the parent instead. And
`mount_app` refuses sub-apps that carry deep page/shell state — [[docs/build-apps/pages-navigation/filesystem-routing|filesystem pages]], OOB regions, fragment targets, sections, a database, or a custom template environment — raising `ConfigurationError`. Register those on the parent directly, or keep the two apps deployed separately.
:::

## When `mount_app` collides

When the sub-app's template globals, filters, providers, error handlers, or severity
overrides clash with the parent's, **the parent wins**. The dropped sub-app entries do not
fail silently — each surfaces as an [[docs/quality/contracts-debugging/categories|INFO contract issue]] in category `mount_app_merge` when you run `app.check()`. Promote them to a
warning or error with `app.override_contract_severity("mount_app_merge", Severity.WARNING)`
if a collision should block startup.

::::{dropdown} Reference: mount_app merge rules and unsupported state
The full merge matrix when `mount_app` hoists a sub-app into its parent:

:::{list-table}
:header-rows: 1

* - Category
  - Rule
* - Routes
  - Paths are prefixed; duplicate paths (after prefixing) fail at `freeze()` via the router's duplicate check.
* - Route names
  - Preserved as-is; cross-app name collisions surface via the `route_names` contract check.
* - Middleware
  - Appended in sub-app order. Parent middleware wraps the sub-app's.
* - Template globals / filters / providers / error handlers / severity overrides
  - **Parent wins.** Dropped sub-app entries recorded as INFO issues in category `mount_app_merge`.
* - Startup / shutdown / worker hooks
  - Appended (parent hooks fire first).
* - Reload dirs
  - Union (deduplicated).
* - Contract checks
  - Appended (order-independent by design).
:::

`mount_app` raises `ConfigurationError` when the sub-app carries deep page or shell state
that would silently break rendering on the parent:

- `mount_pages(...)`-discovered routes, metadata, templates, and layout chains
- Registered sections, OOB regions, fragment targets, layout presets, and live blocks
- A custom template environment, database, or migrations directory

If you hit this, register those on the parent directly or keep the two apps deployed
separately. Wider sub-app composition is tracked for a future release.
::::{/dropdown}

## `mount_app` is a migration tool

Once the refactor that motivated `mount_app` is done, collapse the sub-app into the parent:
move its routes, middleware, and hooks inline. Chained `mount_app` calls work, but the
result is harder to reason about than one flat app. If the merge wires up authentication
across feature areas, check the [[docs/quality/deployment/auth-hardening|secure-by-default middleware stack]] before you ship.

:::{note} See also
- [[docs/build-apps/pages-navigation/routes|Routes]] — register handlers directly on one app
- [[docs/build-apps/pages-navigation/filesystem-routing|Filesystem routing]] — `mount_pages` and page discovery
- [[docs/quality/contracts-debugging/categories|Contract categories]] — what `mount_app_merge` and other `app.check()` issues mean
:::
