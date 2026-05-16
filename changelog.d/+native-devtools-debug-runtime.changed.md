**DevTools** — Chirp DevTools now uses native debug runtime wiring and server-owned EventStream traces instead of replacing browser `EventSource`.

  Internal debug/reload routes are classified as framework-owned, hidden from normal DevTools activity by default, and protected from application route collisions at freeze time. Debug responses also include typed return traces so DevTools can report the negotiated `Template`, `Fragment`, `PageComposition`, `OOB`, `Suspense`, `Stream`, `EventStream`, `Action`, or `ValidationError` branch without parsing response bodies.
