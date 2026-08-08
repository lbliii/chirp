# Orrery

Railway dogfood host for **N wrapped skills** (issue #985 / epic #964). One
Chirp process mounts `gaze`, `resolve`, and `star` via `mount_skills`, serves
an aggregated `/mcp` + `/skills` discovery, and a hypermedia `/console`. The
home page streams live invocations from `ToolEventBus` so an agent call shows
up immediately.

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

# Invoke look_at — watch `/` show the call
curl -s http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -H 'mcp-protocol-version: 2026-07-28' \
  -H 'mcp-method: tools/call' \
  -H 'mcp-name: look_at' \
  -d '{"jsonrpc":"2.0","method":"tools/call","id":2,"params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{}},"name":"look_at","arguments":{"target":"Vega"}}}'
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
