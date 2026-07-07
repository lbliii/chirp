"""Chirp DevTools lifecycle compatibility proof for htmx 2 and htmx 4."""

import asyncio
from pathlib import Path

from chirp import OOB, App, AppConfig, Fragment, Request, Response, Template
from chirp.middleware.csp_nonce import CSPNonceMiddleware

TEMPLATES_DIR = Path(__file__).parent / "templates"
PREVIEW_TEMPLATES_DIR = Path(__file__).parent / "preview_templates"

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

preview_app = App(
    config=AppConfig(
        template_dir=PREVIEW_TEMPLATES_DIR,
        htmx=True,
        htmx_version="4.0.0-beta5",
        debug=True,
    )
)
preview_app.add_middleware(CSPNonceMiddleware(style_unsafe_inline=True))


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


@preview_app.route("/")
def preview_index():
    return Template("preview.html", result="Ready")


@preview_app.route("/swap", methods=["POST"])
def preview_swap():
    return Fragment("preview.html", "result", result="Swapped")


@preview_app.route("/inherit")
def preview_inherit():
    return Fragment("preview.html", "inherited", inherited="Inherited")


@preview_app.route("/validation")
def preview_validation():
    return Response(
        b'<div id="validation">Validation failed</div>',
        status=422,
        content_type="text/html",
    )


@preview_app.route("/failure")
def preview_failure():
    return Response(
        b'<main id="shell">Shell destroyed</main>',
        status=500,
        content_type="text/html",
    )


@preview_app.route("/oob")
def preview_oob():
    return OOB(
        Fragment("preview.html", "main_result", result="Main updated"),
        Fragment(
            "preview.html",
            "oob_result",
            target="oob-result",
            swap="innerHTML",
            result="OOB updated",
        ),
    )


@preview_app.route("/delete", methods=["DELETE"])
async def preview_delete(request: Request):
    form = await request.form()
    item = request.query.get("item") or form.get("item", "missing")
    return Fragment("preview.html", "delete_result", item=item)


@preview_app.route("/slow")
async def preview_slow():
    await asyncio.sleep(0.2)
    return Fragment("preview.html", "slow_result", result="Too late")


@preview_app.route("/queue", methods=["POST"])
async def preview_queue():
    await asyncio.sleep(0.15)
    return Fragment("preview.html", "queue_result", result="Queued")


@preview_app.route("/history/next")
def preview_history():
    return Fragment("preview.html", "history", result="History next")


if __name__ == "__main__":
    app.run()
