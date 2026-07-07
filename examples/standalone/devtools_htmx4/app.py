"""Chirp DevTools lifecycle compatibility proof for htmx 2 and htmx 4."""

from pathlib import Path

from chirp import OOB, App, AppConfig, Fragment, Request, Response, Template

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


def _page_context(*, version: str, compat: bool) -> dict[str, object]:
    return {
        "version": version,
        "compat": compat,
        "result": "Ready",
        "count": 0,
        "target_raw": "",
        "target_id": "",
        "source_raw": "",
        "source_id": "",
        "source_tag": "",
        "trigger": "",
        "trigger_name": "",
        "request_type": "",
        "accept": "",
    }


@app.route("/")
def index():
    return Template("index.html", **_page_context(version="2", compat=False))


@app.route("/v4")
def htmx4():
    return Template("index.html", **_page_context(version="4", compat=False))


@app.route("/v4-compat")
def htmx4_compat():
    return Template("index.html", **_page_context(version="4", compat=True))


@app.route("/inspect", methods=["POST"])
def inspect(request: Request):
    return Fragment(
        "index.html",
        "metadata",
        target_raw=request.htmx_target or "",
        target_id=request.htmx_target_id or "",
        source_raw=request.htmx_source or "",
        source_id=request.htmx_source_id or "",
        source_tag=request.htmx_source_tag or "",
        trigger=request.htmx_trigger or "",
        trigger_name=request.htmx_trigger_name or "",
        request_type=request.htmx_request_type or "",
        accept=request.headers.get("accept", ""),
    )


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
