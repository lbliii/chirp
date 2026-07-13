<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: markdown

Keep Markdown rendering optional, explicit about safety, and aligned with examples that install the extra.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Markdown rendering and filters remain optional and explicit about dependency and safety behavior. | P1 | machine-backed | `uv run pytest tests/test_markdown.py -q` (`markdown-suite`) |

## Guardrails

- Markdown output never silently bypasses template safety.
- Trusted versus untrusted content assumptions remain documented.

## Edges

- serves → **ai** (optional model-output rendering)
- reviewed-by → **security** (escaping assumptions)

## Owns

- **code:** `src/chirp/markdown/`
- **tests:** `tests/test_markdown.py`
- **docs:** `README.md`
