# Custom Middleware

A runnable companion to the middleware docs. It includes a function-based timing
middleware and a class-based rate limiter, showing how to write reusable
request/response interception logic in Chirp.

## Run

```bash
PYTHONPATH=src python examples/standalone/custom_middleware/app.py
```

## Test

```bash
pytest examples/standalone/custom_middleware/
```
