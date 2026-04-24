# RFC 005: `mount_app` — Composing Two Chirp Apps Under a Prefix

**Status:** Draft
**Author:** (proposal)
**Created:** 2026-04-23

---

## 1. Problem Statement

`app.mount(prefix, plugin)` requires a plugin with a `register(app, prefix)` method (`src/chirp/app/__init__.py:491-501`). Users going through migrations — specifically the one that prompted this feedback, dashboard → console architecture — want to compose two full Chirp Apps on the same port without learning the plugin protocol.

The current paper cut:

```python
console_app = App(AppConfig(...))
@console_app.route("/new-view")
def v(request): ...

# This fails with ConfigurationError: "must have a register(app, prefix) method"
dashboard_app.mount("/console", console_app)
```

The user's workaround is usually "flatten both into one App and live with the merge pain," which defeats the point of keeping them separate during a migration.

---

## 2. Non-Goals

- **Not full ASGI composition.** We are not turning Chirp into a mount-any-ASGI-app framework. Two nested ASGI apps would mean two middleware stacks per request, two `app.check()` lifecycles, two template environments. All of those compose badly enough that a shallow copy-routes approach is strictly clearer.
- **Not mounting frozen apps.** `mount_app` takes a setup-phase App (pre-freeze). A sub-app that has already served a request elsewhere is a bug the caller needs to fix, not a state `mount_app` should reason about.
- **Not a permanent pattern.** `mount_app` is a transitional tool. Once a migration is done, the sub-app should typically be collapsed into the parent's route tree. The docs will say this.

---

## 3. Design Decisions

### 3.1 Semantics: hoist-pending, not runtime-compose

**Decision:** `mount_app(prefix, sub_app)` hoists `sub_app`'s **pending** state into `self`, prefixes route paths, and consumes `sub_app`. After the call, `sub_app` is not runnable independently.

Concretely:

1. `self._check_not_frozen()` — parent must be in setup phase.
2. Verify `sub_app` is also in setup phase (not frozen). Raise `ConfigurationError` with a clear message if already frozen.
3. Walk `sub_app._mutable_state.pending_routes`, prefix each `path`, append to `self._mutable_state.pending_routes`. Preserve `name` (subject to name-collision rules — see 3.3).
4. Merge template globals, filters, contract checks, sections, OOB registry entries, fragment-target registry entries, middleware, reload dirs — per the rules in 3.3.
5. Mark `sub_app` as consumed: set a flag that `sub_app.freeze()` / `sub_app.run()` will detect and raise `RuntimeError` with a message pointing back at the `mount_app` call site.

**Rationale:**
- One compiled app, one middleware stack, one `app.check()` run. No request-time composition tax.
- Collision rules (3.3) are explicit instead of implicit-by-ordering.
- The "sub-app is consumed" flag prevents users from accidentally running the sub-app standalone after mounting it — which would give stale behavior.

**Rejected alternative:** Runtime ASGI composition, where both apps freeze independently and the parent dispatches by prefix. Rejected because (a) middleware ordering becomes a two-stack nightmare (Session+CSRF in both? only one? parent's wraps child's or vice versa?), (b) template globals from sub-app aren't visible in parent templates, which is almost never what the user expects, (c) debugging is harder — `app.check()` can't cross the boundary.

### 3.2 Path prefixing

```python
def _prefixed(path: str, prefix: str) -> str:
    normalized_prefix = "/" + prefix.strip("/")
    if path == "/":
        return normalized_prefix
    return normalized_prefix + ("" if path.startswith("/") else "/") + path.lstrip("/")
```

- Prefix `""` or `/` is rejected: `ConfigurationError("mount_app prefix must be a non-root path, e.g. '/admin'")`. Mounting at root has no effect vs. just adding the routes.
- Prefix is stored on each hoisted route's path string, not as a separate field — keeps the routing trie unaware of "this came from a sub-app." Post-hoist, there is no sub-app; there are only routes.
- Sub-app route `/` → `/{prefix}`. Sub-app route `/x` → `/{prefix}/x`. Catch-all routes (`/{path:path}`) in the sub-app are hoisted as-is under the prefix.

### 3.3 Collision rules

Five categories of state must be merged. Rule of thumb: **parent wins** when the user has explicitly registered something in both; warn when both had the same value.

| Category | Parent has | Sub-app has | Rule |
|----------|-----------|-------------|------|
| **Route path** | Yes | Yes (after prefixing) | ERROR — same duplicate-route check that `Router.add` already raises (`src/chirp/routing/router.py:181-187`). No silent shadowing. |
| **Route name** (RFC 003) | Yes | Yes | ERROR via `route_names` contract check — consistent with RFC 003 §3.3. |
| **Template global** | Yes | Yes | Parent wins. `setdefault` on merge; record the skipped sub-app entry as an INFO contract issue in category `mount_app_merge` so it's visible without being fatal. |
| **Template filter** | Yes | Yes | Parent wins. Same INFO rule. |
| **Middleware** | Yes (same class) | Yes (same class) | Parent's instance wins. Sub-app's instance is dropped; INFO contract issue. This covers the common case (both use `SessionMiddleware`). |
| **Middleware** | Any | Any (different classes) | Append sub-app middleware to parent's list, in sub-app order. Parent's middleware wraps sub-app's. |
| **Contract checks** | Yes | Yes | Always append. Contract checks are idempotent / order-independent by design. |
| **Sections, OOB registry, fragment targets** | Same key in both | | ERROR — these are deep contracts; silent override would break shell rendering. Message tells the user to rename or un-register on one side. |
| **Reload dirs** | | | Always append. |

**Rationale for parent-wins on globals/filters/middleware:** The user invoking `mount_app` owns the final app. Their explicit registrations should not be overridden by sub-app defaults. `setdefault` already demonstrates this pattern for template globals (RFC 004 §3.5).

### 3.4 Signature

```python
class App:
    def mount_app(self, prefix: str, sub_app: "App") -> None: ...
```

- Positional args only: `prefix`, `sub_app`. No kwargs in v1 — collision rules are fixed.
- Returns `None`. No "handle" to the mounted app (it's consumed).
- Lives on `App`, not `AppRegistry` — it's a high-level composition, not a setup primitive.

### 3.5 Sub-app consumption flag

Add a field to `MutableAppState`:

```python
consumed_by_mount_app: bool = False
consumed_at_prefix: str | None = None
```

In `App.freeze()` and `App.run()`, check the flag:

```python
if self._mutable_state.consumed_by_mount_app:
    msg = (
        f"This App was consumed by mount_app(prefix={self._mutable_state.consumed_at_prefix!r}) "
        f"and cannot be frozen or run independently. "
        f"If you meant to keep it standalone, remove the mount_app call."
    )
    raise RuntimeError(msg)
```

---

## 4. Worked Example

```python
# console_app.py
console_app = App(AppConfig(template_dir="console/templates"))

@console_app.route("/", name="console.home")
async def home(request):
    return Template("home.html")

@console_app.route("/users/{user_id}")
async def user(request, user_id: int):
    return Template("user.html", user_id=user_id)

console_app.add_middleware(ConsoleAuthMiddleware())
console_app.template_global("console_theme")(lambda: "dark")
```

```python
# dashboard_app.py
dashboard_app = App(AppConfig(template_dir="dashboard/templates"))

@dashboard_app.route("/")
async def index(request):
    return Template("index.html")

dashboard_app.add_middleware(SessionMiddleware(...))
dashboard_app.add_middleware(CSRFMiddleware(...))

dashboard_app.mount_app("/console", console_app)
dashboard_app.run()
```

After `mount_app`:

- `/` → dashboard home
- `/console` → console home (name: `"console.home"`)
- `/console/users/{user_id}` → console user detail
- Request stack for `/console/**`: `SessionMiddleware` → `CSRFMiddleware` → `ConsoleAuthMiddleware` → route handler.
- `console_theme` template global is available in both dashboard and console templates.
- `console_app.run()` raises `RuntimeError` (consumed).

---

## 5. Interactions

### 5.1 With RFC 003 (named routes)

Sub-app route names flow through unchanged. `url_for("console.home")` (RFC 004) resolves to `/console` because the hoisted route's path is prefixed but its name is preserved.

If the sub-app's page discovery assigned the default name `"users.user_id"` and the parent already has a route named `"users.user_id"`, the `route_names` contract check fires at `app.check()` — user chooses who renames.

### 5.2 With `mount(prefix, plugin)`

Both coexist:
- `mount` for reusable packaged pieces (DocsPlugin, auth, etc.) — the plugin author controls `register(app, prefix)` and decides what to expose.
- `mount_app` for "I have two apps and need them on one port, for now." User controls the sub-app's full surface.

Docs will include a side-by-side comparison (parent plan Sprint 4 Task 4.2).

---

## 6. Open Questions

- **OQ-1:** Should sub-app's `on_startup` / `on_shutdown` hooks be hoisted? Recommend **yes** — they're part of the sub-app's lifecycle promise. Append to parent's lists in order.
- **OQ-2:** Should the sub-app's `template_dir` (a different directory) still be usable after mounting? Recommend **yes** — add the sub-app's `FileSystemLoader` to the parent's template environment during hoist. If both apps register loaders for the same directory, dedup.
- **OQ-3:** What if the sub-app called `mount_app` itself (chained composition)? Recommend **yes, allowed** — hoisting is a single-pass copy, so a chain collapses cleanly as long as each link is pre-freeze. Document the pattern.
- **OQ-4:** Error handler collisions (`app.error(404)` in both) — parent wins, like middleware? Recommend **yes** — same rule for consistency.

---

## 7. Acceptance Criteria for Sprint 4 Task 4.1

`tests/test_mount_app.py` covers:

- Two apps with disjoint routes mount cleanly; both routes are reachable under the prefix.
- Mounting at `/` or `""` raises `ConfigurationError`.
- Duplicate route path (after prefixing) raises `ConfigurationError` (via `Router.add`'s existing duplicate check).
- Sub-app middleware runs for requests hitting the prefix.
- Sub-app template globals are available in parent templates.
- After `mount_app`, calling `sub_app.freeze()` or `sub_app.run()` raises `RuntimeError`.
- Parent wins on template-global collision; INFO contract issue is emitted in category `mount_app_merge`.
- Sub-app's `on_startup` hooks run during parent's startup.
