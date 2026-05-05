"""Litestar benchmark app — JSON, CPU, DB, and template workloads."""

from jinja2 import Environment
from litestar import Litestar, get

from benchmarks.apps.workloads import (
    JINJA_TEMPLATE,
    JSON_PAYLOAD,
    TEMPLATE_ITEMS,
    TEMPLATE_TITLE,
    cpu_work,
    fetch_db_rows,
)

template = Environment(autoescape=True).from_string(JINJA_TEMPLATE)


@get("/json", sync_to_thread=True)
def json_handler() -> dict[str, int | str]:
    return JSON_PAYLOAD


@get("/cpu", sync_to_thread=True)
def cpu_handler() -> dict[str, int | str]:
    cpu_work()
    return {"message": "done", "result": 1}


@get("/db", sync_to_thread=True)
def db_handler() -> dict[str, list[dict[str, int | str]]]:
    return {"rows": fetch_db_rows()}


@get("/template", media_type="text/html", sync_to_thread=True)
def template_handler() -> str:
    return template.render(title=TEMPLATE_TITLE, items=TEMPLATE_ITEMS)


app = Litestar(route_handlers=[json_handler, cpu_handler, db_handler, template_handler])
