# Hacker News Live Reader

A live Hacker News front page that pulls real stories from the HN Firebase API.
Scores and comment counts update in real-time — you'll see numbers flash orange
as they change. Click any story to navigate into a threaded comment view with a
smooth cross-fade transition. The whole thing is server-rendered HTML. Zero
client-side JavaScript beyond htmx.

## What it demonstrates

- **Real API** — `httpx.AsyncClient` consuming the HN Firebase API (free, no auth)
- **EventStream + OOB swaps** — SSE pushes score/comment updates to specific DOM elements
- **Recursive templates** — Comment trees rendered with kida's `{% def %}` (self-calling functions)
- **View Transitions** — Cross-fade when navigating list→detail (scoped to avoid OOB swap flicker)
- **Fragment caching** — `{% cache %}` for the site header
- **Lifecycle hooks** — `@app.on_worker_startup` / `@app.on_worker_shutdown` for HTTP client management
- **Multi-worker Pounce** — 4 worker threads with free-threading

## Architecture

```
Browser (htmx + SSE)
    ↓ GET /
Chirp handler
    ↓ Return cached stories from memory
    ↓ Template("hackernews.html", stories=..., page="list")
Browser renders story list, opens SSE connection

SSE loop (every ~5s):
    ↓ httpx GET hacker-news.firebaseio.com/v0/item/{id}.json
    ↓ Compare score/descendants with cached version
    ↓ If changed: yield Fragment("hackernews.html", "story_meta", story=updated)
    ↓ htmx OOB-swaps the matching #meta-{id} div
Browser: score flashes orange, number updates in place

Click story:
    ↓ GET /story/{id} (htmx fragment request)
    ↓ Fetch story + comment tree from HN API (concurrent, depth=2)
    ↓ Render with recursive {% def render_comment(comment, depth) %}
    ↓ View Transition cross-fades the page content
```

## Run

From the b-stack workspace root:

```bash
uv run python chirp/examples/hackernews/app.py
```

Or from this directory:

```bash
uv run python app.py
```

Open http://127.0.0.1:8000 and watch the scores update.

## What to look for

1. **The orange flash** — Leave the page open. Every few seconds, a story's score
   or comment count will update and briefly flash orange. That's a server-pushed
   HTML fragment replacing the element in place.

2. **Click a story's comment count** — The page cross-fades to a threaded comment
   view. No full page reload, no JavaScript router. Just HTML + CSS View Transitions.

3. **The pulsing "LIVE" badge** — Top-right of the header. Confirms the SSE
   connection is active.

4. **Open DevTools → Network** — Filter by `EventSource`. You'll see an initial
   `event: ping` (connection confirm), then `event: fragment` frames when scores
   change. That's the server doing the work, not the browser.

## Zero JavaScript

The real-time behavior is three HTML attributes:

```html
<div hx-ext="sse" sse-connect="/events">
    <div sse-swap="fragment"></div>
</div>
```

The score updates use out-of-band targeting:

```html
<!-- Server pushes this fragment via SSE -->
<div id="meta-12345" hx-swap-oob="outerHTML">
    142 points · by user · 2 hours ago · 37 comments
</div>
```

htmx finds the element with `id="meta-12345"` anywhere on the page and replaces it.
The CSS animation fires because a new element entered the DOM.

No React. No npm. No virtual DOM diffing. Just the browser doing what browsers do.

## Sharp edges and lessons

| Issue | Cause | Fix |
|-------|-------|-----|
| Content flicker on load | SSE sent an OOB fragment immediately; page already had that content, so htmx replaced it with itself | Send `ping` event instead of fragment on connect |
| **Whole node tree wiped** on any SSE update | `sse-connect` inherits `hx-target="#main"` from parent; fragment gets swapped into `#main` instead of the sink | Add `hx-disinherit="hx-target hx-swap"` on `sse-connect` |
| Whole page erased on score update | `view-transition-name` on `#main` caused View Transitions API to run on every OOB swap (a child of `#main`) | Scope `view-transition-name` to `.story-detail` only; list view has no transition so OOB updates don't trigger it |
| List flickers, content disappears on score update | `transition:true` on `#main`'s `hx-swap` — htmx wraps swaps in View Transitions; OOB swaps to children trigger it | Remove `transition:true` from `#main`; put it only on nav links (story, back, comments) |
| `ModuleNotFoundError: chirp` | Running `python` instead of `uv run python` — wrong venv | Use `uv run` from workspace root |
| Outdated deps | chirp had `bengal-pounce>=0.1.0`, `patitas>=0.1.0` | Bumped to match bengal: `>=0.2.0`, `>=0.3.0` |

These were mostly **our implementation choices** (initial fragment, view-transition scope) and **outdated docs** (run instructions, lifecycle hook names). The stack (chirp, kida, patitas, pounce, htmx) is solid; the integration patterns needed tuning.
