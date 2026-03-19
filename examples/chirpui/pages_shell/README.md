# Pages Shell

A small mounted-pages example for Chirp's current routing story. It shows a
persistent `chirp-ui` shell, `_context.py` cascade, route-scoped shell actions,
`page_root` for boosted list navigation, and `Suspense` on a nested detail page.

**Shell actions patterns:**
- **Cascade + remove:** `projects/{slug}/` removes `new-project` from parent
- **mode="replace":** `projects/{slug}/settings/` replaces all zones (Save/Cancel only)
- **Overflow menu:** Parent has Archive, Export, Docs in the overflow dropdown

## Run

```bash
PYTHONPATH=src python examples/chirpui/pages_shell/app.py
```

Open `http://127.0.0.1:8000/projects`.

## Test

```bash
pytest examples/chirpui/pages_shell/
```
