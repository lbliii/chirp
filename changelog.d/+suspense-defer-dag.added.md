**Suspense defer execution DAG** — `AppCompiler` now freezes an explicit
per-route Suspense defer plan (deferred keys, leaf blocks after ancestor
pruning, and `feeds`/`couples` edges) for concurrent independent resolution
and future defer-independence contract checks. No new public return types.
