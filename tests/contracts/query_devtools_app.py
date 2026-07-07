"""Browser fixture app for HTTP QUERY DevTools proof."""

from pathlib import Path

from chirp import App, AppConfig, Page, Stream, ValidationError

_TEMPLATES = Path(__file__).parent / "templates" / "query_rendering"
_QUERY_MEDIA_TYPES = ("application/x-www-form-urlencoded",)

app = App(
    AppConfig(
        debug=True,
        htmx=True,
        skip_contract_checks=True,
        template_dir=_TEMPLATES,
    )
)


@app.route("/")
def index() -> Page:
    return Page(
        "page.html",
        "content",
        page_block_name="page_root",
        message="query-browser-ready",
        notice="ready",
    )


@app.route("/query/page", methods=["QUERY"], query_media_types=_QUERY_MEDIA_TYPES)
def page_query() -> Page:
    return Page(
        "page.html",
        "content",
        page_block_name="page_root",
        message="query-browser-fragment",
        notice="ready",
    )


@app.route("/query/stream", methods=["QUERY"], query_media_types=_QUERY_MEDIA_TYPES)
def stream_query() -> Stream:
    return Stream("stream.html", value="query-browser-stream")


@app.route("/query/invalid", methods=["QUERY"], query_media_types=_QUERY_MEDIA_TYPES)
def invalid_query() -> ValidationError:
    return ValidationError(
        "page.html",
        "content",
        retarget="#query-target",
        message="query-browser-invalid",
    )
