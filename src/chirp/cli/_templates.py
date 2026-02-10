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
    <title>{{% block title %}}{{{{ greeting }}}}{{% endblock %}}</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    {{% block content %}}{{% endblock %}}
</body>
</html>
"""

INDEX_HTML = """\
{{% extends "base.html" %}}

{{% block content %}}
    <h1>{{{{ greeting }}}}</h1>
{{% endblock %}}
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
    <title>{{{{ greeting }}}}</title>
</head>
<body>
    <h1>{{{{ greeting }}}}</h1>
</body>
</html>
"""
