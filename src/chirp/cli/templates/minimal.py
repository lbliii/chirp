"""Minimal project scaffolding templates (--minimal)."""

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
