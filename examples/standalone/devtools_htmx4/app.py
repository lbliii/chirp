"""Chirp DevTools lifecycle compatibility proof for htmx 2 and htmx 4."""

from pathlib import Path

from chirp import OOB, App, AppConfig, Fragment, Response, Template

TEMPLATES_DIR = Path(__file__).parent / "templates"

# Each page provisions its selected htmx build explicitly. Chirp still owns the
# debug runtime and every server response remains a typed HTML return value.
app = App(
    config=AppConfig(
        template_dir=TEMPLATES_DIR,
        htmx=False,
        debug=True,
        islands=True,
        view_transitions=True,
    )
)


@app.route("/")
def index():
    return Template("index.html", version="2", compat=False, result="Ready", count=0)


@app.route("/v4")
def htmx4():
    return Template("index.html", version="4", compat=False, result="Ready", count=0)


@app.route("/v4-compat")
def htmx4_compat():
    return Template("index.html", version="4", compat=True, result="Ready", count=0)


@app.route("/swap", methods=["POST"])
def swap():
    return OOB(
        Fragment("index.html", "result", result="Swapped"),
        Fragment("index.html", "counter", target="counter", swap="outerHTML", count=1),
    )


@app.route("/failure", methods=["POST"])
def failure():
    return Response(b'<p id="failed">Server failed</p>', status=503, content_type="text/html")


if __name__ == "__main__":
    app.run()
