<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: settings

Keep runtime-mutable operator settings explicit, typed, observable, and separate from frozen public AppConfig.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Runtime settings parsing, registration, revision, storage, and change notification remain distinct from AppConfig. | P1 | machine-backed | `uv run pytest tests/test_settings_registry.py -q` (`settings-suite`) |

## Guardrails

- Settings mutation uses the registry/store lifecycle rather than weakening AppConfig immutability.
- File and database stores preserve revision and conflict behavior.

## Edges

- separate-from → **public** (frozen AppConfig)
- observed-by → **app** (runtime lifecycle)

## Owns

- **code:** `src/chirp/settings/`
- **tests:** `tests/test_settings_registry.py`
- **docs:** `docs/`
