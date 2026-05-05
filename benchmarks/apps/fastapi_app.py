"""FastAPI benchmark app — JSON, CPU, and template workloads."""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from jinja2 import Environment

from benchmarks.apps.workloads import (
    JINJA_TEMPLATE,
    JSON_PAYLOAD,
    TEMPLATE_ITEMS,
    TEMPLATE_TITLE,
    cpu_work,
)

app = FastAPI()
template = Environment(autoescape=True).from_string(JINJA_TEMPLATE)


@app.get("/json")
def json_handler():
    return JSON_PAYLOAD


@app.get("/cpu")
def cpu_handler():
    cpu_work()
    return {"message": "done", "result": 1}


@app.get("/template", response_class=HTMLResponse)
def template_handler():
    return template.render(title=TEMPLATE_TITLE, items=TEMPLATE_ITEMS)
