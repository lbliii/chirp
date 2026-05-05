"""Chirp benchmark app — JSON, CPU, and template workloads."""

import os

from kida import DictLoader, Environment

from benchmarks.apps.workloads import (
    JSON_PAYLOAD,
    KIDA_TEMPLATE,
    TEMPLATE_ITEMS,
    TEMPLATE_TITLE,
    cpu_work,
)
from chirp import App, AppConfig, Template

# worker_mode from CHIRP_WORKER_MODE (sync | async | auto) for benchmark variants
worker_mode = os.environ.get("CHIRP_WORKER_MODE", "auto")
# Normalized config: no request queue (avoids 503s under burst, matches FastAPI/Flask)
# safe_target=False, sse_lifecycle=False so fused sync path can run (no middleware)
app = App(
    AppConfig(
        debug=False,
        workers=10,
        request_queue_enabled=False,
        worker_mode=worker_mode,
        safe_target=False,
        static_dir=None,
        sse_lifecycle=False,
    ),
    kida_env=Environment(loader=DictLoader({"bench.html": KIDA_TEMPLATE})),
)


@app.route("/json")
def json_handler() -> dict:
    return JSON_PAYLOAD


@app.route("/cpu")
def cpu_handler() -> dict:
    cpu_work()
    return {"message": "done", "result": 1}


@app.route("/template")
def template_handler() -> Template:
    return Template("bench.html", title=TEMPLATE_TITLE, items=TEMPLATE_ITEMS)
