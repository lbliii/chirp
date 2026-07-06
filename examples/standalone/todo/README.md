# Todo

A persistent todo list backed by `chirp.data` and SQLite. `Page` negotiates the
same template into a full page for normal navigation or the `todo_list` block
for htmx navigation. Mutations use `FormAction` for focused htmx fragments and
a 303 redirect for plain form posts; `ValidationError` keeps inline errors in
the same block. The form carries both CSRF state and standard `method`/`action`
attributes.

## Run

```bash
pip install "bengal-chirp[sessions]"
PYTHONPATH=src python examples/standalone/todo/app.py
```

## Test

```bash
pytest examples/standalone/todo/
```

This is stage 1 of the
[full-application journey](../../../site/content/docs/tutorials/full-application-journey.md).
