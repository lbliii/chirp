"""Shell project scaffolding templates (--shell)."""

SHELL_APP_PY = """\
import os

from chirp import App, AppConfig
from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware
from chirp.middleware.security_headers import SecurityHeadersMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware

_DEFAULT_SECRET = "change-me-before-deploying"
_secret = os.environ.get("CHIRP_SECRET_KEY", _DEFAULT_SECRET)

# Env-driven so the generated app can run in any environment:
#   CHIRP_ENV=production   selects the production security contract track.
#   CHIRP_DEBUG=1          enables dev tooling (defaults on outside production).
_env = os.environ.get("CHIRP_ENV", "development")
_debug = os.environ.get("CHIRP_DEBUG", "1" if _env != "production" else "0") not in (
    "0",
    "false",
    "False",
    "",
)

config = AppConfig.from_env(
    secret_key=_secret,
    template_dir="pages",
    env=_env,
    debug=_debug,
)
app = App(config=config)

if config.env != "development" and config.secret_key == _DEFAULT_SECRET:
    msg = (
        "Refusing to start in production with default secret key. "
        "Set CHIRP_SECRET_KEY to a strong random value."
    )
    raise RuntimeError(msg)

app.add_middleware(
    SessionMiddleware(
        SessionConfig(
            secret_key=config.secret_key,
            # secure defaults to "auto": Secure cookies in production/staging
            # (resolved from AppConfig.env at freeze), off in local dev.
            httponly=True,
            samesite="lax",
        )
    )
)
app.add_middleware(CSRFMiddleware(CSRFConfig()))
app.add_middleware(SecurityHeadersMiddleware())

app.mount_pages("pages")

if __name__ == "__main__":
    app.run()
"""

SHELL_CONTEXT_PY = """\
def context(request) -> dict:
    return {"current_path": request.path}
"""

SHELL_LAYOUT_HTML = """\
{# target: body #}
{# outlet: main #}
{% extends "chirp/layouts/shell.html" %}
{% block head %}
<link rel="stylesheet" href="/static/style.css">
{% end %}
{% block shell %}
<header style="padding:1rem;border-bottom:1px solid #e2e8f0">
    <a href="/" style="font-weight:600">{{ current_path or "App" }}</a>
</header>
<main id="main" hx-boost="true" hx-target="#main"
      hx-swap="innerHTML" hx-select="#page-content">
    <div id="page-content">
        {% block content %}{% end %}
    </div>
</main>
{% end %}
"""

SHELL_LAYOUT_CHIRPUI_HTML = """\
{# target: body #}
{# outlet: main #}
{% extends "chirpui/app_shell_layout.html" %}
{% block head_extra %}
<link rel="stylesheet" href="/static/theme.css">
{% end %}
{% block brand %}{{ current_path or "App" }}{% end %}
{% block sidebar %}
{% from "chirpui/sidebar.html" import sidebar, sidebar_link, sidebar_section %}
{% call sidebar() %}
{% call sidebar_section("Main") %}
{{ sidebar_link("/", "Home") }}
{{ sidebar_link("/items", "Items") }}
{% end %}
{% end %}
{% end %}
"""

SHELL_PAGE_PY = """\
from chirp import Template


def get() -> Template:
    return Template("page.html")
"""

SHELL_PAGE_HTML = """\
{% extends "_layout.html" %}
{% block content %}
<h1>Welcome</h1>
<p>Persistent shell with hx-select. Navigate to /items for inner shell example.</p>
{% end %}
"""

SHELL_ITEMS_LAYOUT_HTML = """\
{# target: items-content #}
{% from "chirp/macros/shell.html" import shell_section %}
<div class="chirpui-shell-section">
    <nav class="chirpui-shell-section__nav">
        <a href="/items">Items</a>
    </nav>
    {% call shell_section("items-content") %}
    {% block content %}{% end %}
    {% end %}
</div>
"""

SHELL_ITEMS_PAGE_PY = """\
from chirp import Template


def get() -> Template:
    return Template("items/page.html")
"""

SHELL_ITEMS_PAGE_HTML = """\
{% extends "items/_layout.html" %}
{% block content %}
<h2>Items</h2>
<p>Inner shell with shell_section macro.</p>
{% end %}
"""
