# Milo MCP Apps named-block resources

This offline example demonstrates issue #578: Chirp renders an existing named
Kida block as a Milo MCP App `ui://` resource through the same template used for
browser and htmx surfaces.

- the caller-owned Milo command receives matching `MCPAppToolMeta` when it is
  originally registered;
- `use_milo()` receives an exact canonical dotted-ID allowlist;
- `adapter.bind()` names one existing Chirp template, named block, and
  parameterless application context provider;
- `app.freeze()` publishes immutable Chirp binding metadata without changing
  the Milo CLI; and
- `@cli.ui_resource` delegates to `adapter.render_resource(...)`, which invokes
  the context provider per read and renders `Fragment` via `App.render`.

Milo 0.4.1 is already installed with Chirp; there is no additional extra.

## Run

```bash
PYTHONPATH=src python examples/standalone/milo_mcp_apps/app.py
```

Open <http://localhost:8000/> for the ordinary Chirp page and
<http://localhost:8000/create-tool> for the shared named block.

## Test

```bash
uv run pytest examples/standalone/milo_mcp_apps -q
```
