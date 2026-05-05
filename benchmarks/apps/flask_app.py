"""Flask benchmark app — JSON, CPU, and template workloads."""

from flask import Flask, jsonify

from benchmarks.apps.workloads import (
    JINJA_TEMPLATE,
    JSON_PAYLOAD,
    TEMPLATE_ITEMS,
    TEMPLATE_TITLE,
    cpu_work,
)

app = Flask(__name__)
template = app.jinja_env.from_string(JINJA_TEMPLATE)


@app.route("/json")
def json_handler():
    return jsonify(JSON_PAYLOAD)


@app.route("/cpu")
def cpu_handler():
    cpu_work()
    return jsonify({"message": "done", "result": 1})


@app.route("/template")
def template_handler():
    return template.render(title=TEMPLATE_TITLE, items=TEMPLATE_ITEMS)
