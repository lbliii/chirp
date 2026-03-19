# Form Get

A tiny example of a plain HTML `GET` form in Chirp. It keeps search state in
the URL, requires no CSRF or JavaScript, and is useful as the smallest example
of bookmarkable query-driven UX.

## Run

```bash
PYTHONPATH=src python examples/standalone/form_get/app.py
```

## Test

```bash
pytest examples/standalone/form_get/
```
