"""Shell project scaffolding templates (--shell)."""

SHELL_APP_PY = """\
from chirp import App, AppConfig

config = AppConfig(template_dir="pages", debug=True)
app = App(config=config)
app.mount_pages("pages")

if __name__ == "__main__":
    app.run()
"""

SHELL_CONTEXT_PY = """\
def context(request) -> dict:
    return {"current_path": request.path}
"""

SHELL_LAYOUT_HTML = """\
{% extends "chirp/layouts/shell.html" %}
{% block head %}
<link rel="stylesheet" href="/static/style.css">
{% end %}
{% block shell %}
<header style="padding:1rem;border-bottom:1px solid #e2e8f0">
    <a href="/" style="font-weight:600">{{ current_path or "App" }}</a>
</header>
<main id="main" hx-boost="true" hx-target="#main"
      hx-swap="innerHTML transition:true" hx-select="#page-content">
    <div id="page-content">
        {% block content %}{% end %}
    </div>
</main>
{% end %}
"""

SHELL_LAYOUT_CHIRPUI_HTML = """\
{% extends "chirpui/app_shell_layout.html" %}
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


async def handler():
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


async def handler():
    return Template("items/page.html")
"""

SHELL_ITEMS_PAGE_HTML = """\
{% extends "items/_layout.html" %}
{% block content %}
<h2>Items</h2>
<p>Inner shell with shell_section macro.</p>
{% end %}
"""
