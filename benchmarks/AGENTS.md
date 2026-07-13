<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: benchmarks

Keep performance workloads, artifacts, comparisons, and claims reproducible, timestamped, versioned, and appropriately caveated.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Core benchmark outputs remain reproducible, versioned, failure-preserving, and explicit about Python GIL mode. | P1 | machine-backed | `uv run pytest tests/test_benchmarks_core.py -q` (`benchmark-contract`) |

## Guardrails

- Synthetic results are not presented as production throughput.
- Fast-path changes carry before/after evidence or explicit no-impact rationale.

## Edges

- measures → **server** (request and sync paths)
- supports → **docs** (performance claims)

## Owns

- **code:** `benchmarks/`
- **tests:** `tests/test_benchmarks_core.py`
- **docs:** `benchmarks/README.md`, `docs/benchmark-*.md`

## Advocate

- Versioned artifacts with environment capture, failure preservation, and explicit synthetic-workload caveats.

## Do Not

- Overclaim production performance or compare mismatched workloads and client limits.
