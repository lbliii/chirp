"""Optimistic apply — the blessed no-build optimistic-UI primitive.

Demonstrates ``optimistic_attrs(...)``: Chirp paints a mutation locally and
instantly from the client's OWN pre-mutation snapshot, lets htmx do the real
request, swaps the authoritative server fragment on success (last-write-wins),
and reverts to the snapshot only when no authoritative fragment lands.

Zero per-client server view state: the ``/toggle-like`` handler is byte-identical
with or without the adapter — it is never told an optimistic apply happened and
allocates nothing per client. The rollback baseline lives in the browser.

Demonstrates:
- AppConfig(islands=True) — ships the blessed optimistic_apply runtime
- optimistic_attrs([...ops]) — declarative, reversible local ops
- Confirm on the authoritative fragment swap (the Like button)
- Revert to the client snapshot when the server fails (the "Save" button)

Run:
    python app.py
"""

from pathlib import Path

from chirp import App, AppConfig, Fragment, Response, Template

TEMPLATES_DIR = Path(__file__).parent / "templates"

config = AppConfig(template_dir=TEMPLATES_DIR, htmx=True, islands=True, debug=True)
app = App(config=config)

# Single-process in-memory demo state (run with one worker).
STATE = {"liked": False, "count": 42}


def _like_context() -> dict[str, object]:
    """Context for the like button, including the optimistic ops for the NEXT
    click (the transition the user is about to make)."""
    liked = STATE["liked"]
    next_liked = not liked
    ops = [
        {"op": "toggleClass", "value": "liked"},
        {"op": "setAttr", "name": "aria-pressed", "value": "true" if next_liked else "false"},
        {"op": "setText", "expr": "+1" if next_liked else "-1", "sel": ".like-count"},
        {"op": "disable"},
    ]
    return {"liked": liked, "count": STATE["count"], "ops": ops}


@app.route("/")
def index():
    return Template("index.html", **_like_context())


@app.route("/toggle-like", methods=["POST"])
def toggle_like():
    """Ordinary mutation. Returns ONLY the authoritative fragment; the optimistic
    paint is confirmed when htmx swaps it in."""
    STATE["liked"] = not STATE["liked"]
    STATE["count"] += 1 if STATE["liked"] else -1
    return Fragment("index.html", "like_button", **_like_context())


@app.route("/save-broken", methods=["POST"])
def save_broken():
    """Always fails. htmx does not swap a 5xx, so the optimistic apply reverts to
    the client's own pre-mutation snapshot."""
    return Response(b"server unavailable", status=503)


if __name__ == "__main__":
    app.run()
