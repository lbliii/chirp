"""FastAPI benchmark app — JSON and CPU workloads."""

from fastapi import FastAPI

app = FastAPI()

JSON_PAYLOAD = {"message": "hello", "count": 42}


def _cpu_work(iterations: int = 50_000) -> int:
    """CPU-bound work: repeated hashing."""
    h = 0
    for i in range(iterations):
        h = hash((h, i))
    return h


@app.get("/json")
def json_handler():
    return JSON_PAYLOAD


@app.get("/cpu")
def cpu_handler():
    _cpu_work()
    return {"message": "done", "result": 1}
