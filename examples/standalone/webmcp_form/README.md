# Declarative WebMCP form

This example adds experimental WebMCP discovery attributes to one real Chirp
form. `TaskForm` remains the typed server contract, `/tasks` remains the only
submission handler, and `FormAction`/`ValidationError` preserve normal and htmx
behavior. The mutation uses the same session-backed CSRF protection for human,
htmx, and browser-agent submissions. There is no imperative browser-tool
registry or JSON response path.

Run it from the repository root:

```bash
PYTHONPATH=src python examples/standalone/webmcp_form/app.py
```

Open `http://127.0.0.1:8000/`. A browser without WebMCP sees and submits the
ordinary form. A compatible browser can discover `tasks.create`, populate the
same controls, and then leaves the mutation for human confirmation because the
form does not emit `toolautosubmit`.

Run its offline proof with:

```bash
pytest examples/standalone/webmcp_form/
```
