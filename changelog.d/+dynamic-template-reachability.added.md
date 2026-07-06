**Dynamic template reachability** — use `app.declare_template(template, blocks=(...))` during setup when a registry selects templates or named blocks at runtime. Chirp normalizes surrounding name whitespace, `app.check()` validates every declared name, and the declaration records the call-site origin without suppressing unrelated dead-template warnings.

  **Migration** — replace unreachable `if False: Page(...)` or `Fragment(...)` reference stubs with the matching `app.declare_template(...)` call.
