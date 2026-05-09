"""Starlette benchmark app — JSON, CPU, DB, and template workloads."""

from jinja2 import Environment
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from benchmarks.apps.workloads import (
    JINJA_TEMPLATE,
    JSON_PAYLOAD,
    TEMPLATE_ITEMS,
    TEMPLATE_TITLE,
    cpu_work,
    fetch_db_rows,
)

template = Environment(autoescape=True).from_string(JINJA_TEMPLATE)


def json_handler(_request):
    return JSONResponse(JSON_PAYLOAD)


def cpu_handler(_request):
    cpu_work()
    return JSONResponse({"message": "done", "result": 1})


def db_handler(_request):
    return JSONResponse({"rows": fetch_db_rows()})


def template_handler(_request):
    return HTMLResponse(template.render(title=TEMPLATE_TITLE, items=TEMPLATE_ITEMS))


app = Starlette(
    routes=[
        Route("/json", json_handler),
        Route("/cpu", cpu_handler),
        Route("/db", db_handler),
        Route("/template", template_handler),
    ]
)
