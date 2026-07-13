<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: templating

Protect one named-block template surface for pages, fragments, OOB, Suspense, streaming HTML, and SSE payloads.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Render plans, OOB blocks, Suspense, navigation swaps, and fragments fail loud instead of producing visible empty swaps. | P0 | machine-backed | `uv run pytest tests/templating tests/test_render_plan_fail_loud.py tests/test_suspense.py tests/test_scoped_oob.py tests/contracts/test_oob_pipeline_e2e.py -q` (`templating-suite`) |
| A missing required named block raises BlockNotFoundError. | P0 | manual | src/chirp/errors.py · `class BlockNotFoundError` |

## Guardrails

- Missing visible blocks fail with BlockNotFoundError rather than empty swaps.
- Layouts compose; page templates do not override sibling layout blocks.
- Stream, Suspense, and EventStream remain distinct contracts.

## Edges

- verified-by → **contracts** (OOB, composition, and defer rules)
- serialized-by → **server** (negotiation)

## Owns

- **code:** `src/chirp/templating/`
- **tests:** `tests/templating/`, `tests/test_suspense.py`, `tests/contracts/test_oob_pipeline_e2e.py`
- **docs:** `docs/hypermedia-footguns.md`, `site/content/docs/build-apps/html-fragments/`

## Advocate

- DOM-level assertions and diagnostics naming template, block, target, route, and registration source.

## Do Not

- Create a partials system, return empty swaps, or use inheritance to override sibling layout blocks.
