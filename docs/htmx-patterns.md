# htmx Patterns Guide

> Chirp-specific recipes for every htmx feature the framework supports.
> Each pattern includes a template example and a reference to the htmx docs.

---

## 1. Loading States — `hx-indicator` + `hx-disabled-elt`

Show a spinner during request flight and disable the triggering element
to prevent double-submits.

**CSS (required once, htmx default convention):**

```css
.htmx-indicator { opacity: 0; transition: opacity 0.2s; }
.htmx-request .htmx-indicator,
.htmx-request.htmx-indicator { opacity: 1; }
```

**Pattern A: Spinner inside button**

```html
<button hx-post="/tasks" hx-swap="none"
        hx-disabled-elt="this" hx-indicator="#adding">
  Add <img id="adding" class="htmx-indicator" src="/static/spinner.svg" alt="">
</button>
```

`hx-disabled-elt="this"` adds the HTML `disabled` attribute during flight.
`hx-indicator="#adding"` targets the spinner by ID.

**Pattern B: Global indicator via parent (inherited)**

```html
<body hx-indicator="#global-spinner">
  <img id="global-spinner" class="htmx-indicator" src="/static/spinner.svg" alt="">
  <!-- All hx-* requests inside <body> show the spinner -->
</body>
```

**htmx ref:** [hx-indicator](https://htmx.org/attributes/hx-indicator/),
[hx-disabled-elt](https://htmx.org/attributes/hx-disabled-elt/)

**Chirp example:** `examples/kanban/templates/board.html`, `examples/todo/templates/index.html`

---

## 2. Race Conditions — `hx-sync`

Prevent stale responses from overwriting fresh ones.

**Search input (abort old, issue new):**

```html
<input type="search" name="q"
       hx-get="/search" hx-target="#results"
       hx-trigger="input changed delay:300ms"
       hx-sync="this:replace">
```

`hx-sync="this:replace"` aborts the in-flight search and replaces it
with the new one. Prevents the older (slower) result from overwriting
the newer one.

**Chat / rapid clicks (first request wins):**

```html
<form hx-post="/chat/send" hx-swap="none"
      hx-sync="this:abort">
```

`hx-sync="this:abort"` means if a send is already in flight, abort the
*new* request. The first one wins.

**Form validation + submit (submit wins):**

```html
<input hx-get="/validate-field" hx-trigger="change"
       hx-sync="closest form:abort">
```

`hx-sync="closest form:abort"` aborts the validation request if the
form is submitted.

**Queue pattern:**

```html
<button hx-post="/action"
        hx-sync="this:queue last">
```

`queue last` processes only the most recent queued request.

**htmx ref:** [hx-sync](https://htmx.org/attributes/hx-sync/)

**Chirp example:** `examples/contacts/templates/contacts.html`, `examples/chat/templates/chat.html`

---

## 3. Progressive Enhancement — `hx-boost`

Convert standard links and forms into AJAX-powered navigation with a
single attribute.

```html
<body hx-boost="true"
      hx-target="#content"
      hx-swap="innerHTML transition:true"
      hx-indicator="#page-loader">
  <header>...</header>
  <main id="content">{% block content %}{% endblock %}</main>
</body>
```

**Behavior:**
- **Links:** AJAX GET, push URL to history, target body, innerHTML swap
- **Forms:** AJAX POST/GET (based on method), NO push URL by default
  (add `hx-push-url="true"` explicitly on forms)
- Only same-domain links are boosted (external links work normally)
- Disable on children: `hx-boost="false"`

**Server-side detection:**

```python
@app.route("/step/1", methods=["POST"])
async def step1(request: Request):
    if request.is_boosted:
        # Could return a targeted fragment for efficiency
        return Fragment("step2.html", "content", ...)
    return Template("step2.html", ...)
```

**htmx ref:** [hx-boost](https://htmx.org/attributes/hx-boost/)

**Chirp example:** `examples/wizard/`, `examples/hackernews/`

---

## 4. Form Validation — `hx-validate` + `ValidationError`

Use HTML5 validation before htmx sends the request.

```html
<form hx-post="/register" hx-validate="true">
  <input name="email" type="email" required>
  <input name="name" required minlength="2">
  <button type="submit">Register</button>
</form>
```

`hx-validate="true"` calls `reportValidity()` before the request. If
validation fails, the browser shows native error messages and htmx does
not send the request.

**Server-side (for validation that can't happen client-side):**

```python
@app.route("/register", methods=["POST"])
async def register(request: Request):
    form = await request.form()
    errors = validate(form)
    if errors:
        return ValidationError("register.html", "form_errors", errors=errors)
    ...
```

**htmx ref:** [hx-validate](https://htmx.org/attributes/hx-validate/)

**Chirp example:** `examples/wizard/templates/step1.html`, `examples/contacts/templates/contacts.html`

---

## 4b. Form Actions — `FormAction`

Handle the form **success** path with progressive enhancement.
`FormAction` auto-negotiates: htmx requests get rendered fragments,
non-htmx requests get a redirect. One return, no branching.

**Before (manual branching):**

```python
@app.route("/contacts", methods=["POST"])
async def add_contact(request: Request, form: ContactForm):
    _add_contact(form.name, form.email)
    contacts = _get_contacts()

    if request.is_fragment:
        return OOB(
            Fragment("contacts.html", "table", contacts=contacts),
            Fragment("contacts.html", "count", target="count", count=len(contacts)),
        )
    return Redirect("/contacts")
```

**After (FormAction):**

```python
from chirp import FormAction, Fragment

@app.route("/contacts", methods=["POST"])
async def add_contact(form: ContactForm):
    _add_contact(form.name, form.email)
    contacts = _get_contacts()

    return FormAction(
        "/contacts",
        Fragment("contacts.html", "table", contacts=contacts),
        Fragment("contacts.html", "count", target="count", count=len(contacts)),
        trigger="contactAdded",
    )
```

**Behavior:**

- **Non-htmx** (standard form submit): 303 redirect to `/contacts`
- **htmx + fragments**: renders the fragments, adds `HX-Trigger: contactAdded`
- **htmx + no fragments**: sends `HX-Redirect` header (client-side redirect)

**Simple redirect (both htmx and non-htmx):**

```python
return FormAction("/dashboard")
```

**Chirp example:** `examples/contacts/app.py`, `examples/kanban/app.py`

---

## 5. URL Management — Attribute vs Response Header

**Attribute (compile-time, static):**

```html
<a href="/page" hx-push-url="true">Go</a>
<a href="/page" hx-replace-url="true">Replace</a>
```

**Response header (runtime, dynamic):**

```python
return Response("ok").with_hx_push_url("/dynamic/path")
return Response("ok").with_hx_replace_url("/replaced")
```

The server header overrides the attribute. `hx-replace-url` replaces the
current history entry instead of pushing a new one.

**htmx ref:** [hx-push-url](https://htmx.org/attributes/hx-push-url/),
[hx-replace-url](https://htmx.org/attributes/hx-replace-url/)

---

## 6. Fragment Selection — Client vs Server

**Server-side (smaller response, more efficient):**

```python
return Fragment("template.html", "block_name", ...)
```

Chirp renders only the specified block. The response is minimal.

**Client-side (server doesn't need to know about the swap):**

```html
<a href="/pokemon/25" hx-select="#pokemon-detail" hx-target="#detail-panel">
  Pikachu
</a>
```

`hx-select` picks an element from the full response on the client.

**Client-side OOB:**

```html
<div hx-select-oob="#alert, #counter:afterbegin">...</div>
```

Pick multiple OOB elements with optional swap strategies.

**Tradeoff:** Server-side is more efficient (smaller response). Client-side
is more flexible (server doesn't need to know about the htmx swap).

**htmx ref:** [hx-select](https://htmx.org/attributes/hx-select/),
[hx-select-oob](https://htmx.org/attributes/hx-select-oob/)

**Chirp example:** `examples/pokedex/templates/pokedex.html`

---

## 7. View Transitions — `transition:true`

Smooth animations between page states using the View Transitions API.

**Automatic (recommended):**

```python
app = App(config=AppConfig(view_transitions=True))
```

One flag. Chirp auto-injects:
- `<meta name="view-transition" content="same-origin">` — browser-native MPA transitions
- `@view-transition { navigation: auto; }` — CSS at-rule
- Default crossfade keyframes (`chirp-vt-out` / `chirp-vt-in`) on `root`
- `htmx.config.globalViewTransitions = true` — every htmx swap uses transitions

Falls back gracefully in browsers without the View Transitions API.
No `transition:true` needed on individual elements when this is enabled.

**Custom per-element transitions:**

For fine-grained control, add `view-transition-name` in your CSS and
`transition:true` on specific swap targets:

```html
<div hx-swap="innerHTML transition:true">...</div>
```

```css
#main { view-transition-name: page-content; }
::view-transition-old(page-content) { animation: slide-out 0.2s; }
::view-transition-new(page-content) { animation: slide-in 0.2s; }
```

**htmx ref:** [View Transitions](https://htmx.org/docs/#view-transitions)

**Chirp example:** `examples/hackernews/templates/hackernews.html`

---

## 8. Preservation — `hx-preserve`

Keep an element's state across swaps.

```html
<video id="bg-video" hx-preserve>
  <source src="/video.mp4" type="video/mp4">
</video>
```

**Requirements:**
- Element must have a stable `id`
- Response must contain an element with the same `id` (content ignored)

**Good candidates:** Video players, iframes, audio elements.

**Bad candidates:** `<input type="text">` (loses focus/caret position).
Use the morphdom extension instead for input preservation.

**htmx ref:** [hx-preserve](https://htmx.org/attributes/hx-preserve/)

---

## 9. Extra Values — `hx-vals`

Send additional parameters without hidden inputs.

**JSON (safe, no eval):**

```html
<button hx-get="/items" hx-vals='{"view": "grid", "sort": "name"}'>
  Grid View
</button>
```

**Dynamic (requires `allowEval`):**

```html
<button hx-get="/items" hx-vals='js:{timestamp: Date.now()}'>
  Refresh
</button>
```

- Overrides `<input>` values with the same name
- Inherited: child declarations override parent

**htmx ref:** [hx-vals](https://htmx.org/attributes/hx-vals/)

**Chirp example:** `examples/pokedex/templates/pokedex.html`

---

## 10. JS API Escape Hatches

For cases where declarative htmx attributes aren't enough.

### `htmx.process(elt)`

Activate htmx on dynamically added DOM elements (outside htmx's swap):

```javascript
// After inserting HTML via innerHTML:
const toast = document.getElementById('toast');
toast.innerHTML = '<button hx-post="/undo">Undo</button>';
htmx.process(toast);  // Enable htmx on the "Undo" button
```

htmx's own swaps call this internally — only needed for manual DOM
manipulation via `innerHTML`, `insertAdjacentHTML`, etc.

### `htmx.trigger(elt, name, detail)`

Fire events from JavaScript that htmx elements can listen to:

```javascript
htmx.trigger(document.body, 'taskDeleted', { taskId: id });
```

```html
<div hx-get="/tasks/last-deleted"
     hx-trigger="taskDeleted from:body"
     hx-target="this"
     hx-swap="innerHTML">
</div>
```

Replaces custom `addEventListener` code with declarative htmx.

### `htmx.ajax(verb, path, context)`

Programmatic htmx-style requests (returns a Promise):

```javascript
htmx.ajax('GET', '/pokemon?page=2', {
    target: '#pokemon-grid',
    swap: 'beforeend',
    select: '#pokemon-grid > *',
}).then(() => console.log('Loaded'));
```

**When to use:** JS-driven triggers (timers, animations, non-DOM events).
For scroll-triggered loading, prefer `hx-trigger="revealed"` instead.

**htmx ref:** [htmx API](https://htmx.org/api/)

**Chirp example:** `examples/kanban/templates/board.html`
