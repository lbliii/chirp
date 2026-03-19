"""Form GET — plain HTML form with action and method="get" (no htmx).

Demonstrates the HTML default pattern for search: a plain form that
submits via GET. No JavaScript, no CSRF, works without htmx.
Chirp contracts validate that action="/" maps to a GET route.

Run:
    python app.py
"""

from pathlib import Path

from chirp import App, AppConfig, Request, Template

TEMPLATES_DIR = Path(__file__).parent / "templates"

config = AppConfig(template_dir=TEMPLATES_DIR)
app = App(config=config)


@app.route("/")
def search(request: Request):
    """Search page — plain form submit via GET."""
    q = request.query.get("q", "")
    results = [f"Item {i}" for i in range(3)] if q else []
    return Template("search.html", query=q, results=results)


if __name__ == "__main__":
    app.run()
