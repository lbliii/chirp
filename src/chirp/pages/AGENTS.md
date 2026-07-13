<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: pages

Keep filesystem route, context, action, section, shell, layout, and reactive conventions executable and safe.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Filesystem discovery, route-directory conventions, shell composition, and page contracts remain executable. | P0 | machine-backed | `uv run pytest tests/test_page_resolve.py tests/test_page_discovery_names.py tests/test_route_directory_contract_e2e.py tests/contracts/test_page_shell.py -q` (`pages-suite`) |

## Guardrails

- Shell targets remain narrow and missing regions fail loud.
- Reactive shared state needs deterministic free-threaded race proof.

## Edges

- registers → **routing** (filesystem routes)
- composes → **templating** (shell and layout plans)

## Owns

- **code:** `src/chirp/pages/`
- **tests:** `tests/test_page_resolve.py`, `tests/test_route_directory_contract_e2e.py`, `tests/contracts/test_page_shell.py`
- **docs:** `docs/hypermedia-footguns.md`, `site/content/docs/build-apps/pages-navigation/`
