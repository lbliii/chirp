<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: pelt

Preserve the pure-Python, libpq-free, free-threading-native PostgreSQL wire driver and its sans-I/O seam.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Pelt framing, messages, codecs, protocol, connection, and pool behavior retain focused coverage. | P0 | machine-backed | `uv run pytest tests/test_pelt -q` (`pelt-suite`) |
| Framing returns a parsed message and length, incomplete input, or ProtocolError for malformed input. | P0 | manual | src/chirp/data/drivers/_pelt/_framing.py · `def parse_message` |

## Guardrails

- Sans-I/O modules touch no socket or anyio.
- Framing returns a message/length, incomplete input, or ProtocolError—never arbitrary failure.
- Never hold a lock across await or I/O.
- Pool and connection signatures remain compatible with Chirp's Database facade.

## Edges

- implements → **data** (PostgreSQL seam)

## Owns

- **code:** `src/chirp/data/drivers/_pelt/`
- **tests:** `tests/test_pelt/`
- **docs:** `tests/docs/test_pelt_conformance_contract.py`

## Advocate

- Sans-I/O fuzzing, free-threaded stress tests, actionable PELT_* errors, and honest benchmark caveats.

## Do Not

- Add compiled extensions, hold locks across I/O, or change the Database seam without coordinated proof.
