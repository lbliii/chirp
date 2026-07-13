<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: app

Guard the boundary where setup-time mutation becomes immutable runtime truth.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Registration, freeze, mounting, runtime publication, and URL generation retain lifecycle coverage. | P0 | machine-backed | `uv run pytest tests/test_app tests/test_app_bind_config.py tests/test_mount_app.py tests/test_url_for.py -q` (`app-lifecycle`) |
| Free-threaded freeze publishes complete runtime state under an explicit lock boundary. | P0 | manual | src/chirp/app/__init__.py · `_freeze_lock` |

## Guardrails

- Freeze publishes a complete runtime state under the free-threaded lifecycle boundary.
- Registration after freeze and serving a consumed mounted app fail loud.

## Edges

- publishes → **routing** (compiled routes)
- snapshots → **contracts** (stable check inputs)

## Owns

- **code:** `src/chirp/app/`
- **tests:** `tests/test_app/`, `tests/test_mount_app.py`, `tests/test_url_for.py`
- **docs:** `docs/routing/mounting.md`, `docs/rfcs/005-mount-app.md`

## Advocate

- Whole-state publication, complete contract snapshots, and deterministic mount/freeze diagnostics.

## Do Not

- Add runtime mutation escape hatches or let checks observe half-published state.
