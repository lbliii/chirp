<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: skill

Keep signed skill envelopes verifiable, provisional, and negotiated as typed return values without a parallel JSON API layer.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Signed Envelope round-trips through negotiate and rejects tampered payloads. | P0 | machine-backed | `uv run pytest tests/test_skill -q` (`skill-suite`) |

## Guardrails

- Envelope remains a frozen slotted return type with structural negotiate dispatch.
- Ed25519 signatures cover all metadata; tampering fails closed.
- chirp.skill stays a provisional submodule API (not re-exported from top-level chirp).

## Edges

- negotiated-by → **server** (Envelope return wire JSON)
- documented-as → **public** (provisional submodule API)
- feeds → **tools** (later skill.tool MCP surface)

## Owns

- **code:** `src/chirp/skill/`
- **tests:** `tests/test_skill/`
- **docs:** `docs/public-api.md`
