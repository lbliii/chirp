# Todo

A persistent todo list backed by `chirp.data` and SQLite. The same template
renders as a full page or an htmx fragment, so add, toggle, and delete actions
work with partial page updates and inline validation.

## Run

```bash
pip install chirp[data]
cd examples/todo && python app.py
```

## Test

```bash
pytest examples/todo/
```
