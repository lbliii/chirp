**Suspense defer coupling check** — `app.check()` now emits env-aware
`defer_coupling` warnings when the freeze-time Suspense DAG reports deferred
keys that share a leaf block (`couples` edges). Silent in development; WARNING
in staging and production. Shared-panel coupling remains a valid pattern —
promote with `app.override_contract_severity("defer_coupling", …)` when
independence is required.
