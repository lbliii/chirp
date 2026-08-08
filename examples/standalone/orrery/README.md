# Orrery

Railway dogfood host for **10 wrapped skills** (issue #985 / epic #964). One
Chirp process mounts the astronomy demos (`gaze`, `resolve`, `star`) alongside
seven signed, deterministic trust-workflow demos via `mount_skills`, serves an
aggregated `/mcp` + `/skills` discovery, and a hypermedia `/console`. The home
page streams live invocations from `ToolEventBus` so an agent call shows up
immediately.

## Trust-workflow skills

The additional skills are intentionally offline-safe examples: they illustrate
the input contract and signed receipt shape without performing network calls or
making live production claims.

| Tool | Illustrative input | Signed demo receipt |
| --- | --- | --- |
| `verify_mcp` | MCP endpoint | transport, protocol, compatibility status |
| `release_readiness` | revision and declared CI state | ready/blocked decision and policy |
| `production_receipt` | deployment name | health state and deployment digest |
| `artifact_qa` | artifact name and required section count | quality checklist result |
| `research_evidence` | research question | fixture evidence-set identifier |
| `handoff_receipt` | change summary and owner | scoped operational handoff |
| `reliability_status` | skill name | fixture smoke and reliability status |

Every MCP result remains signed by its owning skill. In a production skill,
these deterministic fields are the place to attach a live verifier, policy
version, source bundle, or observed state—while retaining the same explicit
tool contract and receipt provenance.

## Run

```bash
PYTHONPATH=src uv run --extra skill --extra sessions \
  python examples/standalone/orrery/app.py
```

Open `/` for the live feed, `/console` to browse manifests, or point an MCP
client at `/mcp`.

```bash
# List tools (modern Streamable HTTP headers)
curl -s http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -H 'mcp-protocol-version: 2026-07-28' \
  -H 'mcp-method: tools/list' \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1,"params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{}}}}'

# Invoke verify_mcp — watch `/` show the signed compatibility receipt
curl -s http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -H 'mcp-protocol-version: 2026-07-28' \
  -H 'mcp-method: tools/call' \
  -H 'mcp-name: verify_mcp' \
  -d '{"jsonrpc":"2.0","method":"tools/call","id":2,"params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{}},"name":"verify_mcp","arguments":{"endpoint":"https://orrery.example/mcp"}}}'
```

Boot runs freeze + smoke against the dogfood corpus so `/console` shows
publish-oracle reliability scores. Set `ORRERY_SKIP_PUBLISH=1` to skip that
during local iteration.

## Test

```bash
pytest examples/standalone/orrery/
```

## Deploy (Railway)

This directory ships a `Dockerfile` and `railway.toml`. Connect the Railway
service to GitHub (`lbliii/chirp`, root directory
`examples/standalone/orrery`) or deploy from this folder with `railway up`.

Required service variables:

| Variable | Value |
| --- | --- |
| `CHIRP_ENV` | `production` |
| `CHIRP_DEBUG` | `0` |
| `CHIRP_SECRET_KEY` | generated secret |
| `CHIRP_LOG_FORMAT` | `json` |
| `GIT_REF` | `main` (or the deploy branch/SHA) |

`AppConfig.from_env()` binds `0.0.0.0:$PORT` on Railway. Healthcheck targets
`/health`. See `docs/deployment/railway.md`.
