# Milo MCP Apps registration preview

This offline example demonstrates the registration-only `chirp.ext.milo`
boundary from issue #577:

- the caller-owned Milo command receives matching `MCPAppToolMeta` when it is
  originally registered;
- `use_milo()` receives an exact canonical dotted-ID allowlist;
- `adapter.bind()` names one existing Chirp template, named block, and
  parameterless application context provider; and
- `app.freeze()` publishes immutable Chirp binding metadata without changing
  the Milo CLI.

Milo 0.4.1 is already installed with Chirp; there is no additional extra.
Issue #578 separately owns invoking the context provider and rendering the
named block as an MCP App resource. The registered resource handler therefore
fails explicitly if invoked instead of returning parallel or placeholder HTML.

## Run

```bash
PYTHONPATH=src python examples/standalone/milo_mcp_apps/app.py
```

Open <http://localhost:8000/> to view the ordinary Chirp page.

## Test

```bash
uv run pytest examples/standalone/milo_mcp_apps -q
```
