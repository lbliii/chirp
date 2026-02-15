"""Hello World — the simplest chirp app.

Demonstrates routes, return-value content negotiation, path parameters,
Response chaining, and custom error handlers.

Run:
    python app.py
"""

from chirp import App, Request, Response

app = App()


@app.route("/")
def index():
    return "Hello, World!"


@app.route("/greet/{name}")
def greet(name: str):
    return f"Hello, {name}!"


@app.route("/api/status")
def status():
    return {"status": "ok", "version": "0.1.1"}


@app.route("/custom")
def custom():
    return Response("Created").with_status(201).with_header("X-Custom", "chirp")


@app.error(404)
def not_found(request: Request):
    return f"Nothing at {request.path}"


if __name__ == "__main__":
    app.run()
