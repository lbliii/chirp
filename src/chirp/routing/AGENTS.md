<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: routing

Keep path matching, route names, converters, mounting, and URL generation deterministic.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Route parsing, matching, naming, mounting, and URL generation remain deterministic and fail loud on ambiguity. | P0 | machine-backed | `uv run pytest tests/test_route.py tests/test_router.py tests/test_params.py tests/test_url_for.py tests/test_mount_app.py tests/contracts/test_routes.py -q` (`routing-suite`) |

## Guardrails

- Ambiguous syntax, names, or match order fail loud rather than depending on fixture order.

## Edges

- receives → **pages** (filesystem-discovered registrations)
- compiled-by → **app** (freeze and mounting)

## Owns

- **code:** `src/chirp/routing/`, `src/chirp/app/url_for.py`, `src/chirp/app/mount.py`
- **tests:** `tests/test_route.py`, `tests/test_router.py`, `tests/test_url_for.py`
- **docs:** `docs/routing/`
