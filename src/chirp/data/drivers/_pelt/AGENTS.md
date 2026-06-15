# Steward: pelt — PostgreSQL wire-protocol driver

You own `chirp.data.drivers._pelt`: a **pure-Python, free-threading-native** PostgreSQL
driver, built in-tree behind the `data-pg` seam and destined for extraction to a standalone
`bengal-pelt` package. Tracked by the pelt saga (GitHub **#252**) and its epics.

Design docs (gitignored, in the workspace `.context/`): `pelt-design-conventions.md` (house
style + module layout + API), `pelt-driver-strategy.md` (options + sizing + roadmap).

## North Star

The only PostgreSQL driver for Python that is **pure-Python, libpq-free, and GIL-off by
construction** — and that gets *faster* under concurrency as cores are added. This is an
**identity/flagship** bet, not a performance bet: pelt will be ~10–20× slower per-row than
asyncpg's Cython on a single thread. That cost is acceptable for hypermedia/OLTP workloads
and is documented, never hidden.

## Non-Negotiables

- **Pure Python. No C/Cython/Rust extension, ever**, and no dependency that ships one. A
  C-extension without the `Py_mod_gil` slot re-enables the GIL interpreter-wide — the exact
  failure pelt exists to avoid. Any future accelerator must be optional *and* declare the slot.
- **The sans-I/O split is sacred.** `_messages` / `_framing` / `_protocol` / `_codecs` /
  `_builder` touch **no socket and no anyio** — bytes in, typed messages / outbound bytes out.
  Only `connection` / `pool` own anyio I/O. This is what makes the core fuzzable and
  FT-parallelizable.
- **Framing never crashes.** `parse_message` returns `(msg, n)`, `(None, 0)`, or raises
  `ProtocolError` — nothing else, on any input. Proven by a Hypothesis fuzz test.
- **Free-threading discipline.** Per-connection state is single-owner (lock-free); config and
  wire messages are frozen (lock-free reads); the codec/statement registries are
  `threading.Lock`-guarded with `MappingProxyType` snapshots and **fail loud on conflict**.
  **Never hold a lock across `await` or I/O.**
- **The Chirp seam contract is load-bearing.** The `Database` facade calls
  `pool.acquire()/release()/close()/size` and `Connection.fetch/fetchrow/execute/`
  `executemany/cursor/transaction`. Do not change these signatures without updating the seam.
- **Errors carry a `PELT_*` code + an actionable hint** and survive pickling.

## Stop-And-Ask

Stop and ask the human before changing any of:

- the public **pool / connection method shape** (the Chirp facade calls it directly);
- **wire-protocol framing / message** parsing or encoding semantics;
- **codec** decode/encode semantics (Python-type outputs the facade's `dict(row)` depends on);
- **prepared-statement / pool lifecycle** (caching keys, eviction, checkout invariants);
- **auth / TLS** behavior (SCRAM-SHA-256, sslmode matrix);
- any **free-threading assumption** (what is single-owner vs frozen vs lock-guarded).

## Done Criteria

- Errors carry a code + a next action; the failure path is tested.
- Malformed wire input is fuzzed (`parse_message` never crashes).
- Hot-path changes carry benchmark evidence (codec / framing loops).
- Shared mutable state is frozen, ContextVar-scoped, or lock-guarded-with-a-documented-reason.
- Concurrency claims are proven with real-thread stress tests under `PYTHON_GIL=0`.
- Tests that close an issue carry `@pytest.mark.issue(N)` (the closure-acceptance gate).

## Own

**Code:** `src/chirp/data/drivers/_pelt/`.
**Tests:** `tests/test_pelt/` (sans-I/O units + fuzz now; integration + concurrency in E4/E6).
**Seam:** `src/chirp/data/drivers/postgres.py` (the one in-tree adapter line).
