**Chirp-ui integration** — Suppress ``UserWarning`` when optional chirp-ui implementations replace Chirp’s built-in filter stubs (detected via ``__module__`` prefix).

**Contract checks** — ``Template``/``Page``/``Suspense``/``Fragment`` reference scan includes ``Page`` and ``Suspense`` paths; filesystem routes expose the original handler as ``Route.page_source_handler`` so dead-template and fragment checks see user source inside the async page wrapper. Import ``make_route_link_attrs`` via ``importlib`` when wiring ``route_link_attrs`` for ty-friendly optional installs.

**Context cascade** — Deduplicate identical override notices; omit INFO when child providers intentionally override ``shell_actions``, ``shell_mode``, or ``Components``.
