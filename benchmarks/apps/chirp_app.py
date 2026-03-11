"""Chirp benchmark app — JSON and CPU workloads."""

import os

from chirp import App, AppConfig

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
    )
)

JSON_PAYLOAD = {"message": "hello", "count": 42}


def _cpu_work(iterations: int = 50_000) -> int:
    """CPU-bound work: repeated hashing."""
    h = 0
    for i in range(iterations):
        h = hash((h, i))
    return h


@app.route("/json")
def json_handler() -> dict:
    return JSON_PAYLOAD


@app.route("/cpu")
def cpu_handler() -> dict:
    _cpu_work()
    return {"message": "done", "result": 1}
