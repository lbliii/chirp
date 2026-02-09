# Pokedex

A browseable Pokedex with a dark-themed card UI and a JSON REST API.
Same frozen dataclasses flow from SQLite through the Query builder to
kida templates (for humans) or JSON (for API consumers). Demonstrates
chirp serving both interfaces from the same app.

## What it demonstrates

- **Dual interface** — HTML UI at `/` and JSON API at `/api/` from the same data layer
- **Pokemon cards** — Type-colored badges, stat previews, legendary markers, detail view with stat bars
- **Search + filter** — htmx-powered search-as-you-type and type filter buttons
- **Pagination** — `Query.take().skip()` with page navigation
- **Page rendering** — Full page or fragment depending on htmx request
- **chirp.data** — SQLite with migrations, `Query` builder, 36 seeded Pokemon
- **API key auth** — Custom middleware protecting `/api/` routes only
- **JSON responses** — `dict`/`list` returns for API endpoints, JSON error handlers
- **CORS** — `CORSMiddleware` for cross-origin API access
- **Template filter** — Custom `type_color` filter for Pokemon type badge colors

## Run

```bash
pip install chirp[data]
cd examples/pokedex && python app.py
```

Open http://127.0.0.1:8000 to browse the Pokedex.

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/health` | No | Health check |
| GET | `/api/pokemon` | Yes | List with pagination + filters |
| GET | `/api/pokemon/{id}` | Yes | Single Pokemon by ID |
| GET | `/api/types` | Yes | All distinct types |
| GET | `/api/stats` | Yes | Aggregate statistics |

## API Usage

```bash
# Health check (no auth)
curl http://127.0.0.1:8000/api/health

# List Pokemon
curl -H "Authorization: Bearer demo-key-change-me" \
     http://127.0.0.1:8000/api/pokemon

# Filter by type
curl -H "Authorization: Bearer demo-key-change-me" \
     "http://127.0.0.1:8000/api/pokemon?type=fire"

# Search
curl -H "Authorization: Bearer demo-key-change-me" \
     "http://127.0.0.1:8000/api/pokemon?q=char"
```
