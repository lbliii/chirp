"""Pokedex — JSON API + browseable HTML UI with chirp.data.

A Pokedex powered by chirp.data: browse Pokemon in the browser with
htmx, or consume the same data as a JSON REST API. Same frozen
dataclasses flow from SQLite through Query builder to template or
JSON — depending on who's asking.

Demonstrates:
- Dual interface: HTML UI at ``/`` and JSON API at ``/api/``
- Pure JSON responses (dict/list returns) for API routes
- Template + Fragment rendering for the browser
- Pagination with Query.take().skip()
- Search and filter via request.query
- chirp.data with SQLite + migrations + seed data
- API key authentication via custom middleware
- JSON error handlers + CORS for API consumers

Run:
    pip install chirp
    python app.py
"""

import math
import os
from dataclasses import dataclass
from pathlib import Path

from chirp import App, AppConfig, Fragment, Page, Request
from chirp.data import Query
from chirp.http.request import Request as RequestType
from chirp.http.response import Response
from chirp.middleware.builtin import CORSConfig, CORSMiddleware
from chirp.middleware.protocol import Next

TEMPLATES_DIR = Path(__file__).parent / "templates"
MIGRATIONS_DIR = Path(__file__).parent / "migrations"
DB_PATH = Path(__file__).parent / "pokedex.db"

_api_key = os.environ.get("API_KEY", "demo-key-change-me")

# ---------------------------------------------------------------------------
# Type colors — for the UI badges
# ---------------------------------------------------------------------------

TYPE_COLORS: dict[str, str] = {
    "normal": "#a8a878",
    "fire": "#f08030",
    "water": "#6890f0",
    "electric": "#f8d030",
    "grass": "#78c850",
    "ice": "#98d8d8",
    "fighting": "#c03028",
    "poison": "#a040a0",
    "ground": "#e0c068",
    "flying": "#a890f0",
    "psychic": "#f85888",
    "bug": "#a8b820",
    "rock": "#b8a038",
    "ghost": "#705898",
    "dragon": "#7038f8",
    "dark": "#705848",
    "steel": "#b8b8d0",
    "fairy": "#ee99ac",
}

# ---------------------------------------------------------------------------
# Data model — frozen dataclass, same object from DB through to template/JSON
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Pokemon:
    id: int
    name: str
    types: str
    hp: int
    attack: int
    defense: int
    speed: int
    generation: int
    legendary: int  # SQLite stores booleans as 0/1


@dataclass(frozen=True, slots=True)
class _TypeRow:
    """Single-column result for DISTINCT types queries."""

    types: str


def _pokemon_to_dict(p: Pokemon) -> dict:
    """Convert a Pokemon dataclass to a JSON-friendly dict."""
    return {
        "id": p.id,
        "name": p.name,
        "types": p.types.split(","),
        "hp": p.hp,
        "attack": p.attack,
        "defense": p.defense,
        "speed": p.speed,
        "generation": p.generation,
        "legendary": bool(p.legendary),
    }


# Reusable base query — immutable, safe at module level
ALL_POKEMON = Query(Pokemon, "pokemon").order_by("id")

# ---------------------------------------------------------------------------
# Shared query logic (used by both HTML and JSON routes)
# ---------------------------------------------------------------------------


async def _query_pokemon(
    *,
    page: int = 1,
    per_page: int = 20,
    type_filter: str = "",
    search: str = "",
) -> tuple[list[Pokemon], int, int]:
    """Run a filtered, paginated Pokemon query.

    Returns (results, total, total_pages).
    """
    offset = (page - 1) * per_page

    query = ALL_POKEMON
    count_query = Query(Pokemon, "pokemon")

    if type_filter:
        query = query.where("(',' || types || ',') LIKE ?", f"%,{type_filter},%")
        count_query = count_query.where("(',' || types || ',') LIKE ?", f"%,{type_filter},%")
    if search:
        query = query.where("name LIKE ?", f"%{search}%")
        count_query = count_query.where("name LIKE ?", f"%{search}%")

    total = await count_query.count(app.db)
    results = await query.take(per_page).skip(offset).fetch(app.db)
    total_pages = max(math.ceil(total / per_page), 1)

    return results, total, total_pages


async def _get_all_types() -> list[str]:
    """Get a sorted list of all distinct Pokemon types."""
    rows = await app.db.fetch(_TypeRow, "SELECT DISTINCT types FROM pokemon ORDER BY types")
    all_types: set[str] = set()
    for row in rows:
        for t in row.types.split(","):
            all_types.add(t.strip())
    return sorted(all_types)


# ---------------------------------------------------------------------------
# API key middleware (only protects /api/ routes)
# ---------------------------------------------------------------------------


class APIKeyMiddleware:
    """Simple bearer token authentication for API endpoints.

    Only protects paths under ``protect`` prefix.  Skips auth for
    explicitly excluded paths (e.g. health check).
    """

    __slots__ = ("_key", "_protect", "_exclude")

    def __init__(
        self,
        key: str,
        protect: str = "/api/",
        exclude: tuple[str, ...] = (),
    ) -> None:
        self._key = key
        self._protect = protect
        self._exclude = exclude

    async def __call__(self, request: RequestType, next: Next) -> Response:
        if not request.path.startswith(self._protect):
            return await next(request)
        if request.path in self._exclude:
            return await next(request)

        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return Response(
                body='{"error": "Missing API key", "status": 401}',
                status=401,
                content_type="application/json",
            )

        token = auth[7:]  # len("Bearer ") == 7
        if token != self._key:
            return Response(
                body='{"error": "Invalid API key", "status": 401}',
                status=401,
                content_type="application/json",
            )

        return await next(request)


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = App(
    config=AppConfig(template_dir=TEMPLATES_DIR, debug=True),
    db=f"sqlite:///{DB_PATH}",
    migrations=str(MIGRATIONS_DIR),
)

app.add_middleware(CORSMiddleware(CORSConfig(
    allow_origins=("*",),
    allow_methods=("GET", "HEAD", "OPTIONS"),
    allow_headers=("Authorization", "Content-Type"),
)))

app.add_middleware(APIKeyMiddleware(
    key=_api_key,
    protect="/api/",
    exclude=("/api/health",),
))

# ---------------------------------------------------------------------------
# Template filter — type badge color
# ---------------------------------------------------------------------------


@app.template_filter("type_color")
def type_color(type_name: str) -> str:
    """Return the CSS color for a Pokemon type."""
    return TYPE_COLORS.get(type_name.lower(), "#777")


# ---------------------------------------------------------------------------
# Error handlers — JSON for API, HTML for browser
# ---------------------------------------------------------------------------


@app.error(404)
def not_found(request: Request):
    return {"error": "Not found", "status": 404}


@app.error(500)
def internal_error(request: Request, exc: Exception):
    return {"error": "Internal server error", "status": 500}


# ---------------------------------------------------------------------------
# HTML routes — browseable UI
# ---------------------------------------------------------------------------


@app.route("/")
async def index(request: Request):
    """Pokedex browser UI — full page or fragment."""
    page = max(request.query.get_int("page", default=1) or 1, 1)
    type_filter = (request.query.get("type") or "").strip().lower()
    search = (request.query.get("q") or "").strip().lower()

    results, total, total_pages = await _query_pokemon(
        page=page, per_page=12, type_filter=type_filter, search=search,
    )
    all_types = await _get_all_types()

    return Page(
        "pokedex.html",
        "pokemon_grid",
        pokemon=results,
        all_types=all_types,
        current_type=type_filter,
        search=search,
        page=page,
        total=total,
        total_pages=total_pages,
    )


@app.route("/pokemon/{pokemon_id}")
async def pokemon_detail(pokemon_id: int, request: Request):
    """Single Pokemon detail view."""
    pokemon = await Query(Pokemon, "pokemon").where("id = ?", pokemon_id).fetch_one(app.db)
    if pokemon is None:
        return ({"error": "Pokemon not found", "status": 404}, 404)

    return Page(
        "pokedex.html",
        "pokemon_detail",
        pokemon=pokemon,
    )


# ---------------------------------------------------------------------------
# JSON API routes — programmatic access
# ---------------------------------------------------------------------------


@app.route("/api/health")
def health():
    """Unauthenticated health check."""
    return {"status": "ok", "service": "pokedex"}


@app.route("/api/pokemon")
async def api_list_pokemon(request: Request):
    """List Pokemon with pagination, type filter, and name search."""
    page = max(request.query.get_int("page", default=1) or 1, 1)
    per_page = min(max(request.query.get_int("per_page", default=20) or 20, 1), 100)
    type_filter = (request.query.get("type") or "").strip().lower()
    search = (request.query.get("q") or "").strip().lower()

    results, total, total_pages = await _query_pokemon(
        page=page, per_page=per_page, type_filter=type_filter, search=search,
    )

    return {
        "data": [_pokemon_to_dict(p) for p in results],
        "meta": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": total_pages,
        },
    }


@app.route("/api/pokemon/{pokemon_id}")
async def api_get_pokemon(pokemon_id: int):
    """Get a single Pokemon by ID."""
    pokemon = await Query(Pokemon, "pokemon").where("id = ?", pokemon_id).fetch_one(app.db)
    if pokemon is None:
        return ({"error": "Pokemon not found", "status": 404}, 404)
    return {"data": _pokemon_to_dict(pokemon)}


@app.route("/api/types")
async def api_list_types():
    """List all distinct Pokemon types."""
    return {"data": await _get_all_types()}


@app.route("/api/stats")
async def api_stats():
    """Aggregate statistics across all Pokemon."""
    total = await ALL_POKEMON.count(app.db)
    avg_hp = await app.db.fetch_val("SELECT ROUND(AVG(hp), 1) FROM pokemon") or 0
    avg_attack = await app.db.fetch_val("SELECT ROUND(AVG(attack), 1) FROM pokemon") or 0
    avg_defense = await app.db.fetch_val("SELECT ROUND(AVG(defense), 1) FROM pokemon") or 0
    avg_speed = await app.db.fetch_val("SELECT ROUND(AVG(speed), 1) FROM pokemon") or 0
    legendary_count = (
        await Query(Pokemon, "pokemon").where("legendary = ?", 1).count(app.db)
    )

    rows = await app.db.fetch(_TypeRow, "SELECT DISTINCT types FROM pokemon")
    type_counts: dict[str, int] = {}
    for row in rows:
        for t in row.types.split(","):
            t = t.strip()
            type_counts[t] = type_counts.get(t, 0) + 1

    return {
        "data": {
            "total": total,
            "legendary_count": legendary_count,
            "averages": {
                "hp": float(avg_hp),
                "attack": float(avg_attack),
                "defense": float(avg_defense),
                "speed": float(avg_speed),
            },
            "types": dict(sorted(type_counts.items())),
        },
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Pokedex")
    print("  http://127.0.0.1:8000")
    print()
    print("  Browser:  http://127.0.0.1:8000")
    print("  API docs: http://127.0.0.1:8000/api/health")
    print()
    print(f"  API Key: {_api_key}")
    print('  Usage:   curl -H "Authorization: Bearer demo-key-change-me" localhost:8000/api/pokemon')
    print()
    app.run()
