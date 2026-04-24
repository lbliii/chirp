# RFC 004: `url_for` — Route Reversal for Templates and Handlers

**Status:** Draft
**Author:** (proposal)
**Created:** 2026-04-23
**Depends on:** RFC 003 (named routes)

---

## 1. Problem Statement

Templates hardcode URLs. When the IA changes, every `hx-get="/contacts/42"` has to be hunted down manually — the user feedback that prompted this work cited 85 such strings in one app.

Chirp has all the pieces to eliminate this:

- `Route.name` is a field on every route and, after RFC 003, is populated by default for page-discovery routes.
- `fragment_url(route_path, block_name)` is already registered as a template global via `setdefault` (`src/chirp/app/compiler.py:349`) — the exact pattern `url_for` should follow.
- `Route.path` is preserved as the original path template (`"/contacts/{contact_id}"`), which is what we need to reverse against.

What's missing is a resolver and a template global.

---

## 2. Non-Goals

- **No absolute URLs in v1.** `url_for` returns path-only strings (e.g. `/contacts/42`). The ASGI `root_path` and reverse proxy handle scheme/host. If we ever need absolute URLs (email templates, webhooks), that's a separate `url_for(..., _external=True)` flag in a future RFC.
- **No route introspection API.** `url_for` is a single forward function: name → URL. It does not expose "does this route exist?" — use a contract check for that.
- **No automatic method suffixing.** Route name is per-route, not per-method. `url_for("contacts.contact_id")` returns the same URL for GET and POST; the method is chosen by the htmx attribute (`hx-get` vs `hx-post`), not by the name.

---

## 3. Design Decisions

### 3.1 Signature

```python
def url_for(name: str, /, **params: Any) -> str
```

- `name` is positional-only (`/`). Prevents `url_for(name="foo")` where users later mistake `name` for a path param.
- All other arguments are keyword. No positional path params — ambiguity-free.
- Return is always a `str` (never `None`). Unknown name raises.

### 3.2 Path vs query binding

Kwargs that match a **path param name** are consumed into the path; leftover kwargs become a URL-encoded query string.

```python
# Route: /contacts/{contact_id}
url_for("contacts.contact_id", contact_id=42)
#   -> "/contacts/42"

url_for("contacts.contact_id", contact_id=42, highlight="email")
#   -> "/contacts/42?highlight=email"

url_for("contacts")
#   -> "/contacts"

url_for("contacts", search="alice", page=2)
#   -> "/contacts?search=alice&page=2"
```

**Resolution algorithm:**

```python
def url_for(name: str, /, **params: Any) -> str:
    route = _routes_by_name.get(name)
    if route is None:
        known = sorted(_routes_by_name)
        msg = f"No route named {name!r}. Known names: {known}"
        raise LookupError(msg)

    segments = parse_path(route.path)   # reuse existing parser
    path_param_names = {s.param_name for s in segments if s.is_param and s.param_name}
    used: set[str] = set()
    rendered: list[str] = []
    for seg in segments:
        if seg.is_param:
            if seg.param_name not in params:
                missing = path_param_names - set(params)
                msg = (
                    f"Missing path parameter(s) {sorted(missing)!r} "
                    f"for route {name!r} (path={route.path!r})"
                )
                raise KeyError(msg)
            value = params[seg.param_name]
            rendered.append(quote(str(value), safe=""))
            used.add(seg.param_name)
        else:
            rendered.append(seg.value)

    path = "/" + "/".join(rendered) if rendered else "/"

    query_params = {k: v for k, v in params.items() if k not in used}
    if not query_params:
        return path
    return f"{path}?{urlencode(query_params, doseq=True)}"
```

**Rationale:**
- Kwargs are the single source of truth for every substitution — no mixed positional + kwarg rules to explain.
- Unconsumed kwargs "fall through" to the query string automatically. A user adding `page=2` to a template call just works; they don't have to remember a separate `query=` kwarg.

### 3.3 Quoting

- **Path values:** `urllib.parse.quote(str(v), safe="")`. Every value is coerced via `str()`; spaces, slashes, and unicode are percent-encoded. `safe=""` is deliberate — if a user wanted a literal `/` in a value, they'd be passing a `{slug:path}` param, which the parser handles separately.
- **Query values:** `urllib.parse.urlencode(params, doseq=True)`. `doseq=True` supports `url_for("x", tag=["a", "b"])` → `?tag=a&tag=b`.

### 3.4 Root path / ASGI prefix

**Decision:** `url_for` returns paths relative to the app root (always starting with `/`). It does **not** consult ASGI `root_path` or any prefix.

- Downstream consumers (ASGI server, reverse proxy) prepend `root_path` for external URLs — same contract as Starlette's `url_path_for`.
- For locale prefixes (`i18n_url_prefix`), the current request-scoped locale is not available at template-render time in a pure `url_for` helper. A separate `locale_url_for` (out of scope) or middleware-aware wrapper can layer on top later.

**Rejected alternative:** Consult `request.scope["root_path"]` inside `url_for`. Would require request-scoped state in every call; couples URL reversal to the request cycle, breaking use in SSE event generators and background templates.

### 3.5 Exposure points

Three surfaces:

1. **Public app method:** `app.url_for(name, **params) -> str`. Useful in handlers, redirects, middleware.
2. **Template global:** `{{ url_for("contacts.contact_id", contact_id=42) }}`. Registered via `setdefault` following `fragment_url` precedent (`src/chirp/app/compiler.py:349`):

   ```python
   self._mutable.template_globals.setdefault("url_for", app.url_for)
   ```

   `setdefault` means a user who registered their own `url_for` via `app.template_global("url_for")` keeps their definition — Invariant 2 of the parent plan.
3. **No module-level import.** We don't ship `from chirp import url_for` — it needs the app's freeze-time index, so it's an app method. Handlers receive `request.app` access via the `Request` (or through the existing context helpers).

### 3.6 Error messages

**Unknown name:**

```
LookupError: No route named 'contacts.detail'. Known names:
  ['contacts', 'contacts.contact_id', 'projects', 'projects.slug']
```

Listing known names inline is critical — the feedback user was grepping and find-replacing; a good error message is the grep.

**Missing path param:**

```
KeyError: Missing path parameter(s) ['contact_id'] for route 'contacts.contact_id' (path='/contacts/{contact_id}')
```

Both exception types subclass existing Python builtins (`LookupError`, `KeyError`) so `try/except LookupError` works. No bespoke exception class needed.

---

## 4. Worked Examples

All four examples are exercised by `tests/test_url_for.py` in Sprint 2 Task 2.2.

**Example 1 — static route, no params:**

```html
<a href="{{ url_for('about') }}">About</a>
<!-- renders: <a href="/about">About</a> -->
```

**Example 2 — path param:**

```html
<!-- page.py: contacts/{contact_id}/page.html -->
<a hx-get="{{ url_for('contacts.contact_id', contact_id=contact.id) }}"
   hx-target="#main">{{ contact.name }}</a>
<!-- contact.id=42 renders: <a hx-get="/contacts/42" ...>Alice</a> -->
```

**Example 3 — path param + query string:**

```python
# In a handler
@app.route("/redirect-to-contact", methods=["GET"])
async def jump(request):
    return Redirect(app.url_for("contacts.contact_id",
                                contact_id=42,
                                highlight="email",
                                tab="activity"))
# -> Redirect("/contacts/42?highlight=email&tab=activity")
```

**Example 4 — query-only, multi-value:**

```html
<a href="{{ url_for('contacts', tag=['vip', 'new'], sort='name') }}">
  Filtered
</a>
<!-- renders: <a href="/contacts?tag=vip&tag=new&sort=name">Filtered</a> -->
```

---

## 5. Interaction with Existing Helpers

### 5.1 `fragment_url`

`fragment_url(route_path, block_name)` takes a raw path, not a name. Composition:

```python
fragment_url(app.url_for("contacts"), "contact_row")
# -> "/_frag/contacts?_b=contact_row"
```

Keeping them separate is intentional — `url_for` reverses names; `fragment_url` wraps paths for fragment dispatch. Two focused helpers compose better than one do-everything helper.

### 5.2 `route_link_attrs` (chirp-ui)

`route_link_attrs` (`src/chirp/ext/chirp_ui.py:148`) emits the full htmx swap-attr bundle for an internal link. It takes an `href` string — which can now be produced by `url_for`:

```html
<a {{ route_link_attrs(url_for("contacts")) }}>Contacts</a>
```

No change to `route_link_attrs` itself.

---

## 6. Open Questions

- **OQ-1:** Should `url_for` error messages include a "did you mean" suggestion via `difflib.get_close_matches`? Tempting, but listing all known names is already informative. Recommend **no** for v1 — trivial to add later if users ask.
- **OQ-2:** Should `None` in kwargs skip the query param (`url_for("x", y=None)` → `/x` instead of `/x?y=None`)? Starlette does skip `None`. Recommend **yes** — surprising behavior otherwise; test in Sprint 2 Task 2.2.
- **OQ-3:** Should path-param values of type `list` raise (you can't put a list in a path segment)? Recommend **yes** with a clear error: "Path parameter 'id' got list; path segments must be scalar."

---

## 7. Acceptance Criteria for Sprint 2 Task 2.2 + 2.3

- `tests/test_url_for.py` covers all four worked examples plus:
  - Unknown name raises `LookupError` whose message contains known names.
  - Missing path param raises `KeyError` whose message names the param and the route path.
  - `None` query-param kwarg is skipped.
  - Duplicate name failing `route_names` check (already specified in RFC 003).
- Template render test: a template using `{{ url_for(...) }}` renders the expected URL.
- Regression: user who `app.template_global("url_for")(my_fn)` keeps `my_fn`, not ours.
