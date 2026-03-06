# Pages Shell

A small mounted-pages example for Chirp's current routing story. It shows a
persistent `chirp-ui` shell, `_context.py` cascade, route-scoped shell actions,
`page_root` for boosted list navigation, and `Suspense` on a nested detail page.

## Run

```bash
cd examples/pages_shell && python app.py
```

Open `http://127.0.0.1:8000/projects`.

## Test

```bash
pytest examples/pages_shell/
```
