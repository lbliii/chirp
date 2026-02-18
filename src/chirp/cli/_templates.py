"""Project scaffolding templates — plain Python strings for ``chirp new``.

No template engine here (that would be circular). Simple ``str.format()``
substitution with ``{name}`` for the project name.
"""

# ---------------------------------------------------------------------------
# Full project (default)
# ---------------------------------------------------------------------------

APP_PY = """\
from chirp import App, Request
from chirp.templating import Template

app = App()


@app.route("/")
async def index(request: Request) -> Template:
    return Template("index.html", greeting="Hello, world!")


if __name__ == "__main__":
    app.run()
"""

BASE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{% block title %}{{ greeting }}{% endblock %}</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    {% block content %}{% endblock %}
</body>
</html>
"""

INDEX_HTML = """\
{% extends "base.html" %}

{% block content %}
    <h1>{{ greeting }}</h1>
{% endblock %}
"""

STYLE_CSS = """\
*,
*::before,
*::after {{
    box-sizing: border-box;
}}

body {{
    font-family: system-ui, -apple-system, sans-serif;
    line-height: 1.6;
    max-width: 40rem;
    margin: 2rem auto;
    padding: 0 1rem;
    color: #1a1a1a;
}}

h1 {{
    font-weight: 600;
}}
"""

TEST_APP_PY = """\
\"\"\"Basic smoke tests for {name}.\"\"\"

from chirp import App
from chirp.testing import TestClient


app = App()


@app.route("/")
async def index():
    return "Hello, world!"


class TestSmoke:
    def test_index(self) -> None:
        client = TestClient(app)
        response = client.get("/")
        assert response.status == 200
"""

# ---------------------------------------------------------------------------
# Minimal project (--minimal)
# ---------------------------------------------------------------------------

MINIMAL_APP_PY = """\
from chirp import App, Request
from chirp.templating import Template

app = App()


@app.route("/")
async def index(request: Request) -> Template:
    return Template("index.html", greeting="Hello, world!")


if __name__ == "__main__":
    app.run()
"""

MINIMAL_INDEX_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>{{ greeting }}</title>
</head>
<body>
    <h1>{{ greeting }}</h1>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# SSE project (--sse, used with full layout)
# ---------------------------------------------------------------------------

SSE_APP_PY = """\
from chirp import App, Request
from chirp.streaming import EventStream, Fragment
from chirp.templating import Template

app = App()


@app.route("/")
async def index(request: Request) -> Template:
    return Template("index.html", greeting="Hello, world!")


@app.route("/stream", referenced=True)
async def stream(request: Request) -> EventStream:
    async def events():
        yield Fragment("index.html", "stream_block", text="Hello from SSE!")

    return EventStream(events())
"""

SSE_INDEX_HTML = """\
{% extends "chirp/layouts/boost.html" %}
{% block title %}{{ greeting }}{% end %}
{% block content %}
<h1>{{ greeting }}</h1>
<div hx-ext="sse" sse-connect="/stream" hx-disinherit="hx-target hx-swap">
  <div sse-swap="stream_block" hx-target="this">
    <span>Waiting for stream...</span>
  </div>
</div>
{% end %}

{% block stream_block %}
<p>{{ text }}</p>
{% end %}
"""

# ---------------------------------------------------------------------------
# V2 project (default) — auth + dashboard + primitives
# ---------------------------------------------------------------------------

V2_APP_PY = """\
import os

from chirp import (
    App,
    AppConfig,
    EventStream,
    Fragment,
    Redirect,
    Request,
    get_user,
    is_safe_url,
    login,
    logout,
)
from chirp.middleware.auth import AuthConfig, AuthMiddleware
from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware
from chirp.middleware.security_headers import SecurityHeadersMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware

from models import load_user, verify_user

_DEFAULT_SECRET = "change-me-before-deploying"
_secret = os.environ.get("CHIRP_SECRET_KEY", _DEFAULT_SECRET)

config = AppConfig(
    secret_key=_secret,
    template_dir="pages",
    debug=True,
)
app = App(config=config)

if not config.debug and config.secret_key == _DEFAULT_SECRET:
    msg = (
        "Refusing to start in production with default secret key. "
        "Set CHIRP_SECRET_KEY to a strong random value."
    )
    raise RuntimeError(msg)

app.add_middleware(
    SessionMiddleware(
        SessionConfig(
            secret_key=config.secret_key,
            secure=not config.debug,
            httponly=True,
            samesite="lax",
        )
    )
)
app.add_middleware(AuthMiddleware(AuthConfig(load_user=load_user)))
app.add_middleware(CSRFMiddleware(CSRFConfig()))
app.add_middleware(SecurityHeadersMiddleware())

app.mount_pages("pages")


@app.route("/login", methods=["POST"])
async def do_login(request: Request):
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")
    user = verify_user(username, password)
    if user:
        login(user)
        next_url = request.query.get("next", "/dashboard")
        return Redirect(next_url if is_safe_url(next_url) else "/dashboard")
    return Redirect("/login?error=1")


@app.route("/logout", methods=["POST"])
def do_logout():
    logout()
    return Redirect("/")


if __name__ == "__main__":
    app.run()
"""

V2_APP_CHIRPUI_PY = """\
import os

from chirp import (
    App,
    AppConfig,
    EventStream,
    Fragment,
    Redirect,
    Request,
    get_user,
    is_safe_url,
    login,
    logout,
    use_chirp_ui,
)
from chirp.middleware.auth import AuthConfig, AuthMiddleware
from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware
from chirp.middleware.security_headers import SecurityHeadersMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware

import chirp_ui
from models import load_user, verify_user

_DEFAULT_SECRET = "change-me-before-deploying"
_secret = os.environ.get("CHIRP_SECRET_KEY", _DEFAULT_SECRET)

config = AppConfig(
    secret_key=_secret,
    template_dir="pages",
    debug=True,
    islands=True,
)
app = App(config=config)

if not config.debug and config.secret_key == _DEFAULT_SECRET:
    msg = (
        "Refusing to start in production with default secret key. "
        "Set CHIRP_SECRET_KEY to a strong random value."
    )
    raise RuntimeError(msg)

app.add_middleware(
    SessionMiddleware(
        SessionConfig(
            secret_key=config.secret_key,
            secure=not config.debug,
            httponly=True,
            samesite="lax",
        )
    )
)
app.add_middleware(AuthMiddleware(AuthConfig(load_user=load_user)))
app.add_middleware(CSRFMiddleware(CSRFConfig()))
app.add_middleware(SecurityHeadersMiddleware())

use_chirp_ui(app)
chirp_ui.register_filters(app)

app.mount_pages("pages")


@app.route("/login", methods=["POST"])
async def do_login(request: Request):
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")
    user = verify_user(username, password)
    if user:
        login(user)
        next_url = request.query.get("next", "/dashboard")
        return Redirect(next_url if is_safe_url(next_url) else "/dashboard")
    return Redirect("/login?error=1")


@app.route("/logout", methods=["POST"])
def do_logout():
    logout()
    return Redirect("/")


@app.route("/time", referenced=True)
async def time_stream(request: Request) -> EventStream:
    import asyncio
    from datetime import datetime

    async def events():
        while True:
            yield Fragment("dashboard/page.html", "time_block", now=datetime.now().isoformat())
            await asyncio.sleep(1)

    return EventStream(events())


if __name__ == "__main__":
    app.run()
"""

V2_MODELS_PY = '''\
from dataclasses import dataclass

from chirp.security.passwords import hash_password, verify_password


@dataclass(frozen=True, slots=True)
class User:
    id: str
    name: str
    password_hash: str
    is_authenticated: bool = True


_DEMO_HASH = hash_password("password")

USERS: dict[str, User] = {
    "admin": User(id="admin", name="Admin", password_hash=_DEMO_HASH),
}


async def load_user(user_id: str) -> User | None:
    return USERS.get(user_id)


def verify_user(username: str, password: str) -> User | None:
    user = USERS.get(username)
    if user and verify_password(password, user.password_hash):
        return user
    return None
'''

V2_LAYOUT_HTML = """\
{# target: body #}
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{% block title %}App{% endblock %}</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    {% set user = current_user() %}
    <nav>
        <a href="/">Home</a>
        {% if user.is_authenticated %}
        <a href="/dashboard">Dashboard</a>
        <form method="post" action="/logout" style="margin:0">
            {{ csrf_field() }}
            <button type="submit">Logout</button>
        </form>
        {% else %}
        <a href="/login">Login</a>
        {% end %}
    </nav>
    {% block content %}{% endblock %}
</body>
</html>
"""

V2_LAYOUT_CHIRPUI_HTML = """\
{# target: body #}
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{% block title %}App{% endblock %}</title>
    <link rel="stylesheet" href="/static/chirpui.css">
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    {% set user = current_user() %}
    {% from "chirpui/layout.html" import container, stack, block %}
    {% call container() %}
    <nav class="chirpui-navbar" style="margin-bottom:1rem">
        <a class="chirpui-navbar__brand" href="/">App</a>
        <div class="chirpui-navbar__links chirpui-navbar__links--end">
        {% if user.is_authenticated %}
        <a href="/dashboard" class="chirpui-navbar__link">Dashboard</a>
        <form method="post" action="/logout" style="margin:0;display:inline">
            {{ csrf_field() }}
            <button type="submit" class="chirpui-btn chirpui-btn--ghost chirpui-btn--sm">Logout</button>
        </form>
        {% else %}
        <a href="/login" class="chirpui-navbar__link">Login</a>
        {% end %}
        </div>
    </nav>
    {% call stack() %}
    {% block content %}{% endblock %}
    {% end %}
    {% end %}
</body>
</html>
"""

V2_INDEX_PAGE_PY = """\
from chirp import Template


async def handler():
    return Template("page.html")
"""

V2_INDEX_HTML = """\
{% extends "_layout.html" %}

{% block content %}
<h1>Welcome</h1>
<p>Sign in to access the dashboard.</p>
{% endblock %}
"""

V2_INDEX_CHIRPUI_HTML = """\
{% extends "_layout.html" %}

{% block content %}
{% from "chirpui/layout.html" import page_header %}
{% call page_header("Welcome", subtitle="Sign in to access the dashboard.") %}
{% end %}
{% endblock %}
"""

V2_LOGIN_PAGE_PY = """\
from chirp import Request, Template


async def handler(request: Request):
    error = request.query.get("error", "")
    return Template("login/page.html", error="Invalid credentials" if error else "")
"""

V2_LOGIN_HTML = """\
{% extends "_layout.html" %}

{% block content %}
<h1>Login</h1>
{% if error %}
<p class="error">{{ error }}</p>
{% end %}
<form method="post" action="/login">
    {{ csrf_field() }}
    <label for="username">Username</label>
    <input type="text" id="username" name="username" required>
    <label for="password">Password</label>
    <input type="password" id="password" name="password" required>
    <button type="submit">Sign in</button>
</form>
<p><small>Hint: admin / password</small></p>
{% endblock %}
"""

V2_LOGIN_CHIRPUI_HTML = """\
{% extends "_layout.html" %}

{% block content %}
{% from "chirpui/layout.html" import page_header, stack, block %}
{% from "chirpui/forms.html" import text_field %}
{% call page_header("Login", subtitle="Sign in to continue") %}
{% end %}
{% if error %}
<p class="chirpui-alert chirpui-alert--error">{{ error }}</p>
{% end %}
{% call stack() %}
<form method="post" action="/login">
    {{ csrf_field() }}
    {% call block() %}
    {% call text_field("username", label="Username", required=true) %}
    {% end %}
    {% call text_field("password", label="Password", type="password", required=true) %}
    {% end %}
    <button type="submit" class="chirpui-btn chirpui-btn--primary">Sign in</button>
</form>
{% end %}
<p class="chirpui-text-muted">Hint: admin / password</p>
{% end %}
{% endblock %}
"""

V2_DASHBOARD_PAGE_PY = '''\
from chirp import Template, get_user, login_required


_GRID_COLUMNS = [{"key": "name", "label": "Name"}, {"key": "role", "label": "Role"}]


@login_required
async def handler():
    return Template("dashboard/page.html", user=get_user(), cols=_GRID_COLUMNS)
'''

V2_DASHBOARD_HTML = """\
{% extends "_layout.html" %}

{% block content %}
<h1>Dashboard</h1>
<p>Welcome, <strong>{{ user.name }}</strong>!</p>
<p>This page is protected by <code>@login_required</code>.</p>
{% endblock %}
"""

V2_DASHBOARD_CHIRPUI_HTML = """\
{% extends "_layout.html" %}

{% block content %}
{% from "chirpui/layout.html" import container, stack, block, page_header %}
{% from "chirpui/card.html" import card %}
{% from "chirpui/state_primitives.html" import draft_store, grid_state %}
{% call page_header("Dashboard", subtitle="Welcome, " ~ user.name) %}
{% end %}
{% call stack() %}
{% call block() %}
{% call card(title="Welcome") %}
<p>Signed in as <strong>{{ user.name }}</strong>.</p>
<form method="post" action="/logout">
    {{ csrf_field() }}
    <button type="submit" class="chirpui-btn chirpui-btn--secondary">Logout</button>
</form>
{% end %}
{% end %}
{% call block() %}
{% call card(title="Notes") %}
{% call draft_store("dashboard_notes", mount_id="notes-root", cls="chirpui-card") %}
<label>Notes</label>
<textarea name="notes" data-draft-field rows="4" style="width:100%;"></textarea>
<p class="chirpui-text-muted">Last saved: <span data-draft-saved-at>never</span></p>
{% end %}
{% end %}
{% end %}
{% call block() %}
{% call card(title="Sample Data") %}
{% call grid_state("demo_grid", cols, mount_id="grid-root", cls="chirpui-card") %}
<input data-grid-filter type="text" placeholder="Filter..." style="width:100%;">
<button type="button" data-grid-sort class="chirpui-btn chirpui-btn--secondary chirpui-btn--sm">Sort</button>
<table>
    <tbody data-grid-body>
    <tr data-grid-row data-grid-id="1"><td data-grid-select><input type="checkbox"></td><td>Alice</td><td>Admin</td></tr>
    <tr data-grid-row data-grid-id="2"><td data-grid-select><input type="checkbox"></td><td>Bob</td><td>User</td></tr>
    <tr data-grid-row data-grid-id="3"><td data-grid-select><input type="checkbox"></td><td>Carol</td><td>Editor</td></tr>
    </tbody>
</table>
{% end %}
{% end %}
{% end %}
{% call block() %}
{% call card(title="Live Clock") %}
<div hx-ext="sse" sse-connect="/time" hx-disinherit="hx-target hx-swap">
    <div sse-swap="time_block" hx-target="this">
        <span>Connecting...</span>
    </div>
</div>
{% end %}
{% end %}
{% end %}
{% endblock %}

{% block time_block %}
<span>{{ now }}</span>
{% endblock %}
"""

V2_STYLE_CSS = """\
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: system-ui, -apple-system, sans-serif;
    background: #0f172a; color: #e2e8f0;
    min-height: 100vh; max-width: 600px; margin: 0 auto; padding: 2rem 1rem;
}}
nav {{
    display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;
    margin-bottom: 2rem; padding-bottom: 1rem; border-bottom: 1px solid #334155;
}}
nav a {{ text-decoration: none; color: #94a3b8; }}
nav a:hover {{ color: #f8fafc; }}
nav form {{ margin-left: auto; }}
.error {{ color: #f87171; margin-bottom: 1rem; font-size: 0.9rem; }}
label {{ display: block; margin-top: 0.75rem; font-weight: 600; color: #f8fafc; }}
input {{
    display: block; width: 100%; padding: 0.5rem 0.75rem; margin-top: 0.25rem;
    background: #1e293b; border: 1px solid #334155; border-radius: 0.5rem;
    color: #e2e8f0;
}}
input:focus {{ outline: none; border-color: #3b82f6; }}
button {{
    padding: 0.5rem 1rem; cursor: pointer; margin-top: 1rem;
    background: #3b82f6; color: #fff; border: none; border-radius: 0.5rem;
}}
button:hover {{ background: #2563eb; }}
small {{ color: #64748b; }}
"""

V2_STYLE_CHIRPUI_CSS = """\
/* Minimal overrides when chirp-ui provides base styles */
"""

V2_CONFTEST_PY = '''\
"""Pytest conftest — add project root to path for app import."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
'''

V2_TEST_APP_PY = """\
\"\"\"Auth flow tests for {name}.\"\"\"

from chirp.testing import TestClient


def _extract_cookie(response, name: str = "chirp_session") -> str | None:
    for hname, hvalue in response.headers:
        if hname == "set-cookie" and hvalue.startswith(f"{{name}}="):
            return hvalue.split(";")[0].partition("=")[2]
    return None


async def test_index_public():
    from app import app
    async with TestClient(app) as client:
        response = await client.get("/")
        assert response.status == 200


async def test_dashboard_requires_login():
    from app import app
    async with TestClient(app) as client:
        response = await client.get("/dashboard")
        assert response.status == 302
        assert "/login" in response.header("location", "")


async def test_login_success():
    from app import app
    async with TestClient(app) as client:
        r1 = await client.get("/login")
        csrf = _extract_csrf_token(r1.text)
        cookie = _extract_cookie(r1)
        assert csrf and cookie
        r = await client.post(
            "/login",
            body=f"username=admin&password=password&_csrf_token={{csrf}}".encode(),
            headers={{
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": f"chirp_session={{cookie}}",
            }},
        )
        assert r.status == 302
        assert "/dashboard" in r.header("location", "")


async def test_login_failure():
    from app import app
    async with TestClient(app) as client:
        r1 = await client.get("/login")
        csrf = _extract_csrf_token(r1.text)
        cookie = _extract_cookie(r1)
        assert csrf and cookie
        r = await client.post(
            "/login",
            body=f"username=admin&password=wrong&_csrf_token={{csrf}}".encode(),
            headers={{
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": f"chirp_session={{cookie}}",
            }},
        )
        assert r.status == 302
        assert "error=1" in r.header("location", "")


async def test_dashboard_authenticated():
    from app import app
    async with TestClient(app) as client:
        r1 = await client.get("/login")
        csrf = _extract_csrf_token(r1.text)
        cookie1 = _extract_cookie(r1)
        assert csrf and cookie1
        r2 = await client.post(
            "/login",
            body=f"username=admin&password=password&_csrf_token={{csrf}}".encode(),
            headers={{
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": f"chirp_session={{cookie1}}",
            }},
        )
        cookie = _extract_cookie(r2)
        assert cookie
        r3 = await client.get("/dashboard", headers={{"Cookie": f"chirp_session={{cookie}}"}})
        assert r3.status == 200
        assert "Admin" in r3.text


async def test_logout():
    from app import app
    async with TestClient(app) as client:
        r1 = await client.get("/login")
        csrf = _extract_csrf_token(r1.text)
        cookie1 = _extract_cookie(r1)
        assert csrf and cookie1
        r2 = await client.post(
            "/login",
            body=f"username=admin&password=password&_csrf_token={{csrf}}".encode(),
            headers={{
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": f"chirp_session={{cookie1}}",
            }},
        )
        cookie = _extract_cookie(r2)
        assert cookie
        r_dash = await client.get("/dashboard", headers={{"Cookie": f"chirp_session={{cookie}}"}})
        csrf2 = _extract_csrf_token(r_dash.text)
        cookie_dash = _extract_cookie(r_dash) or cookie
        r3 = await client.post(
            "/logout",
            body=f"_csrf_token={{csrf2}}".encode(),
            headers={{
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": f"chirp_session={{cookie_dash}}",
            }},
        )
        assert r3.status == 302
        r4 = await client.get("/dashboard", headers={{"Cookie": _extract_cookie(r3) or ""}})
        assert r4.status == 302


async def test_csrf_required():
    from app import app
    async with TestClient(app) as client:
        r = await client.post(
            "/login",
            body=b"username=admin&password=password",
            headers={{"Content-Type": "application/x-www-form-urlencoded"}},
        )
        assert r.status == 403


def _extract_csrf_token(html: str) -> str | None:
    import re
    m = re.search(r'name="_csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else None
"""
