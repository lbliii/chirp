"""FastHTML benchmark app — JSON, CPU, DB, and native FT rendering workloads."""

import secrets

from fasthtml.common import (
    H1,
    FastHTML,
    HTMLResponse,
    JSONResponse,
    Li,
    Main,
    Span,
    Strong,
    Ul,
    to_xml,
)

from benchmarks.apps.workloads import (
    JSON_PAYLOAD,
    TEMPLATE_ITEMS,
    TEMPLATE_TITLE,
    cpu_work,
    fetch_db_rows,
)

app = FastHTML(
    default_hdrs=False,
    htmx=False,
    surreal=False,
    canonical=False,
    sess_cls=None,
    secret_key=secrets.token_hex(32),
)


@app.get("/json")
def json_handler() -> JSONResponse:
    return JSONResponse(JSON_PAYLOAD)


@app.get("/cpu")
def cpu_handler() -> JSONResponse:
    cpu_work()
    return JSONResponse({"message": "done", "result": 1})


@app.get("/db")
def db_handler() -> JSONResponse:
    return JSONResponse({"rows": fetch_db_rows()})


@app.get("/template")
def template_handler() -> HTMLResponse:
    document = Main(
        H1(TEMPLATE_TITLE),
        Ul(*(Li(Span(item.name), Strong(item.value)) for item in TEMPLATE_ITEMS)),
    )
    return HTMLResponse(to_xml(document, indent=False))
