"""Sign in — GET shows the form, POST authenticates (the auth showcase).

Lucky Cat is public-browse / gated-trading: this is the one page that turns an
anonymous visitor into the signed-in demo trader. It is the canonical Chirp auth
flow, return-type-driven end to end:

* **GET /login** renders the centred sign-in card into the app shell. It honours
  a ``?next=`` hop (set by ``@login_required`` when an anonymous user hits a
  gated route) so a successful sign-in returns them where they were headed.
* **POST /login** verifies the credentials against ``users.authenticate``:
  - **bad credentials → ``ValidationError`` (422)** re-renders just the
    ``login_form`` block with the username preserved — the return-type-as-intent
    signature pattern, no full-page nav (the form self-overrides the boosted
    shell outlet so the 422 lands in place; see DESIGN.md §5 footgun #2);
  - **good credentials → ``login()`` + ``FormAction``** to the safe ``next``
    target. ``FormAction`` (with no fragments) is the right dual-mode redirect:
    for an htmx request it emits ``HX-Redirect`` with **no ``Location``**, so
    htmx does a **full** ``window.location`` page load (required for the
    persistent topbar to repaint its auth state — Sign in → user menu, and the
    $MEOW balance / bell / Deposit appear; a boosted ``#main``-only swap would
    not); a plain (no-JS) POST gets a 303. ``hx_redirect``/``Redirect`` are the
    wrong tools here: a 303 + ``Location`` is auto-followed by htmx's XHR before
    it can act on ``HX-Redirect``, so it swaps the followed page in place and the
    URL never changes.

``login()`` regenerates the session (anti-fixation) and stores the user id;
``AuthMiddleware`` (wired in ``app.py``) loads it back on every later request via
``users.get``. POST is CSRF-protected by the shared secure stack (the form ships
``csrf_field()`` and the shell sets ``X-CSRF-Token`` on htmx requests).
"""

import users

import session_store
from chirp import FormAction, Page, Request, ValidationError, is_safe_url, login
from chirp.middleware.sessions import get_session


def _safe_next(raw: str | None) -> str:
    """Honour ``next`` only when it is a safe (relative, same-origin) URL."""
    candidate = (raw or "").strip()
    return candidate if candidate and is_safe_url(candidate) else "/"


def get(request: Request) -> Page:
    """Render the sign-in card (prefilled demo creds keep the live demo 1-click)."""
    return Page(
        "login/page.html",
        "page_content",
        page_block_name="page_root",
        errors=None,
        form={"username": users.DEMO_USERNAME, "password": users.DEMO_PASSWORD},
        next_url=_safe_next(request.query.get("next")),
        demo_creds=f"{users.DEMO_USERNAME} / {users.DEMO_PASSWORD}",
    )


async def post(request: Request) -> Page | ValidationError:
    """Authenticate. Bad creds → 422 re-render; good creds → full-page redirect."""
    form = await request.form()
    username = (form.get("username") or "").strip()
    password = form.get("password") or ""
    next_url = _safe_next(form.get("next"))

    user = users.authenticate(username, password)
    if user is None:
        # Return-type-as-intent: a 422 re-renders ONLY the login_form block with
        # the username preserved (password cleared). The form self-overrides the
        # boosted-shell outlet (hx-select="#login-form") so it lands in place.
        return ValidationError(
            "login/page.html",
            "login_form",
            errors={"_form": ["That username and password didn't match. Try again."]},
            form={"username": username, "password": ""},
            next_url=next_url,
            demo_creds=f"{users.DEMO_USERNAME} / {users.DEMO_PASSWORD}",
        )

    # Regenerates the session (anti-fixation) + stores the user id. Preserve the
    # per-visitor store key (#285) so concurrent demo tabs keep separate wallets.
    store_key = get_session().get("__store_key")
    login(user)
    session = get_session()
    if isinstance(store_key, str) and store_key:
        session["__store_key"] = store_key
    else:
        session_store.ensure_store_key()
    return FormAction(next_url)
