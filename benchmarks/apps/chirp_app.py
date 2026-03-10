"""Chirp benchmark app — JSON and CPU workloads."""

from chirp import App, AppConfig

app = App(AppConfig(debug=False, workers=10))

JSON_PAYLOAD = {"message": "hello", "count": 42}


def _cpu_work(iterations: int = 50_000) -> int:
    """CPU-bound work: repeated hashing."""
    h = 0
    for i in range(iterations):
        h = hash((h, i))
    return h


@app.route("/json")
def json_handler():
    return JSON_PAYLOAD


@app.route("/cpu")
def cpu_handler():
    _cpu_work()
    return {"message": "done", "result": 1}
