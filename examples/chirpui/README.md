# ChirpUI Examples

These examples cover the ChirpUI and app-shell lane: component-driven layouts, boosted navigation, shell updates, and richer interactions on top of core Chirp.

They are the reference point for:

- `use_chirp_ui(app)`
- `AppConfig(..., delegation=True)` where needed
- app shell layouts and shell actions
- boosted navigation and shell-aware fragment behavior

## Run From Repo Root

```bash
# From the repo root:
source .venv/bin/activate
PYTHONPATH=src python examples/chirpui/pages_shell/app.py
```

## Representative Examples

- `contacts_shell`: ChirpUI shell companion to the standalone contacts CRUD example
- `pages_shell`: mounted pages and shell actions
- `shell_oob`: app shell with AST-driven OOB updates
- `islands_shell`: islands inside a shell-aware layout
- `kanban_shell`: full app-shell workflow with auth and live updates
- `rag_demo`: richer AI/documentation experience using the newer UI layer

## Inventory

- `contacts_shell`
- `islands_shell`
- `kanban_shell`
- `llm_playground`
- `pages_shell`
- `rag_demo`
- `shell_oob`
- `sortable_reorder`

## Validation Expectation

These examples should prove the newer shell/UI layer, but they should not redefine baseline standalone Chirp behavior. If a pattern works here and not in standalone, document it as a ChirpUI capability rather than a core Chirp assumption.
