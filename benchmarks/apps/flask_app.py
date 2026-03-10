"""Flask benchmark app — JSON and CPU workloads."""

from flask import Flask, jsonify

app = Flask(__name__)

JSON_PAYLOAD = {"message": "hello", "count": 42}


def _cpu_work(iterations: int = 50_000) -> int:
    """CPU-bound work: repeated hashing."""
    h = 0
    for i in range(iterations):
        h = hash((h, i))
    return h


@app.route("/json")
def json_handler():
    return jsonify(JSON_PAYLOAD)


@app.route("/cpu")
def cpu_handler():
    _cpu_work()
    return jsonify({"message": "done", "result": 1})
