# Todo

A persistent todo list backed by `chirp.data` and SQLite. `Page` negotiates the
same template into a full page for normal navigation or the `todo_list` block
for htmx navigation, while mutations return focused fragments with inline
validation.

## Run

```bash
pip install chirp[data]
PYTHONPATH=src python examples/standalone/todo/app.py
```

## Test

```bash
pytest examples/standalone/todo/
```
