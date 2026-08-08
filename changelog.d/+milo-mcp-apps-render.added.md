**Milo MCP App named-block resources** — `MiloMCPAppAdapter.render_resource()`
invokes the bound parameterless context provider per `ui://` read and renders
the existing Kida named block through `Fragment` / `App.render`, preserving
fail-loud `BlockNotFoundError` and rejecting empty or non-mapping context
without a parallel template or JSON view model.
