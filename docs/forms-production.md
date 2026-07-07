# Production Form Patterns

Server-rendered products usually start simple and then accumulate the hard
cases: login forms, repeated fields, multiple submit buttons, htmx fragments,
plain browser fallback, CSRF, and mounted page handlers. Chirp has the pieces;
the reliable path is to keep those pieces explicit and checkable.

## Baseline Stack

For POST, PUT, PATCH, or DELETE forms in production:

```python
from chirp import App, AppConfig
from chirp.middleware.csrf import CSRFMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware

app = App(AppConfig(secret_key=SECRET_KEY, debug=False))
app.add_middleware(SessionMiddleware(SessionConfig(secret_key=SECRET_KEY)))
app.add_middleware(CSRFMiddleware())
```

`CSRFMiddleware` requires session state. Add `SessionMiddleware` before
`CSRFMiddleware`; `app.check()` reports `csrf_session` when the order is wrong
and `csrf_form` when a static mutating form is missing a rendered CSRF field
while CSRF middleware is active.

In templates, render the field inside every mutating form:

```html
<form method="post">
  {{ csrf_field() }}
  ...
</form>
```

If you configure `CSRFConfig(field_name="csrf")`, `csrf_field()` renders that
configured field name for the active request and `app.check()` accepts the
same field in static form scans. Routes listed in `CSRFConfig.exempt_paths`
are also skipped by the `csrf_form` check.

Do not solve missing CSRF fields by rewriting arbitrary rendered HTML. Keep the
field visible in the template that owns the form so review, tests, and
`app.check()` can reason about it.

## Typed Binding

Prefer frozen/slotted dataclasses with `form_from()` or `form_or_errors()`:

```python
from dataclasses import dataclass

from chirp import Request, ValidationError, form_from


@dataclass(frozen=True, slots=True)
class ReplyForm:
    body: str
    mention_ids: list[int]


async def post(request: Request):
    form = await form_from(request, ReplyForm)
    ...
```

Repeated HTML fields bind to list-typed dataclass fields:

```html
<input type="checkbox" name="mention_ids" value="1">
<input type="checkbox" name="mention_ids" value="2">
```

This is safer than manually checking every possible `getlist` spelling in
product code.

## Mounted Page Contracts

Mounted filesystem pages should declare the form contract on the source
handler, not on generated wrappers:

```python
from chirp.contracts import FormContract, contract


@contract(form=FormContract(ReplyForm, "threads/detail.html", "reply_form"))
async def post(request: Request):
    form = await form_from(request, ReplyForm)
    ...
```

`app.check()` and the route explorer should both show that the mounted POST
route has a contract. If those disagree, the wrapper/source contract bridge is
broken and should be fixed in Chirp.

## Multi-Intent Forms

When one page has several submit intents, use a single explicit field such as
`intent` or `_action` and keep the dispatch local to the handler:

```html
<button type="submit" name="intent" value="save">Save</button>
<button type="submit" name="intent" value="publish">Publish</button>
```

```python
form_data = await request.form()
intent = form_data.get("intent")
match intent:
    case "save":
        ...
    case "publish":
        ...
    case _:
        return ValidationError("studio.html", "editor_form", errors={"intent": ["Unknown action"]})
```

Use one dataclass per intent when the field sets differ materially. A shared
dataclass is fine when the intent changes behavior but not shape.

## Htmx And Plain Browser Fallback

Do not branch on htmx just to choose a different response shape. Let return
types do that work:

- `ValidationError` returns a 422 form fragment for htmx and keeps errors
  structured.
- `MutationResult` or `FormAction` can express "update this fragment, then
  redirect or swap" without hand-writing headers.
- `Redirect` keeps normal and boosted navigation behavior aligned.

Branch only when the page truly has different product behavior for htmx and
non-htmx clients.

## Experimental Declarative WebMCP Forms

`WebMCPForm` can project an explicitly opted-in `FormContract` into the
declarative WebMCP preview without adding another route, handler, schema, or
JavaScript registry. The browser still submits the same real form through the
normal HTTP/htmx path.

```python
from dataclasses import dataclass, field

from chirp import WebMCPForm
from chirp.contracts import FormContract, contract


@dataclass(frozen=True, slots=True)
class TaskForm:
    title: str = field(metadata={
        "webmcp_control": "text",
        "webmcp_description": "Short task title",
        "webmcp_min_length": 1,
        "webmcp_max_length": 80,
    })
    priority: int = field(default=2, metadata={
        "webmcp_control": "number",
        "webmcp_description": "Priority from one to three",
        "webmcp_min": 1,
        "webmcp_max": 3,
    })


@app.route("/tasks", methods=["POST"])
@contract(form=FormContract(
    TaskForm,
    "tasks.html",
    "task_form",
    webmcp=WebMCPForm("tasks.create", "Create a task"),
))
async def create_task(request):
    form = await form_from(request, TaskForm)
    ...
```

Render the compiled attributes on the existing form and controls:

```html
{% block task_form %}
<form method="post" action="/tasks"{{ webmcp_form_attrs("tasks.create") }}>
  {{ csrf_field() }}
  <input{{ webmcp_control_attrs("tasks.create", "title") }}>
  <input{{ webmcp_control_attrs("tasks.create", "priority") }}>
  <button type="submit">Create</button>
</form>
{% end %}
```

The helpers derive names, descriptions, requiredness, scalar defaults, and
supported native constraints from the dataclass. The first preview supports
text, email, search, telephone, URL, and number inputs. File, select, textarea,
checkbox, radio, callable defaults, missing descriptions, and incompatible
Python types fail during app freeze with a concrete field-level error.

`toolautosubmit` is closed by default and is rejected on mutation routes.
Browsers without WebMCP ignore the extra attributes and retain the complete
human form. Keep CSRF, authorization, validation, `FormAction`, and htmx
negotiation on the server exactly as they were before projection.

## Production Checklist

- Add `SessionMiddleware` before `CSRFMiddleware`.
- Render `{{ csrf_field() }}` in every mutating form.
- Bind request data with `form_from()` or `form_or_errors()` where a dataclass
  shape exists.
- Declare `FormContract` for mounted POST page handlers.
- Use explicit `intent`/`_action` fields for multi-intent forms.
- Test full-page and htmx fragment paths for validation failures.
- Keep experimental WebMCP mutation forms human-confirmed; never enable
  `toolautosubmit` on POST/PUT/PATCH/DELETE routes.
- Keep redirects local and safe; preserve scoped `next` values deliberately.

## Startup Diagnostics

`app.check()` uses these categories for production form wiring:

- `csrf_session`: `CSRFMiddleware` is missing `SessionMiddleware` or runs before
  it.
- `csrf_form`: CSRF middleware is active and a static mutating form has no
  token field.
- `form`: a declared `FormContract` disagrees with the template's fields.
- `form_contract`: a static mutating form targets a POST route without a
  declared `FormContract`.
