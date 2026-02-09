"""Tests for the Pokedex — HTML UI + JSON API with auth, pagination, search."""

from chirp.testing import TestClient

_AUTH = {"Authorization": "Bearer demo-key-change-me"}
_BAD_AUTH = {"Authorization": "Bearer wrong-key"}


# ── HTML UI ──────────────────────────────────────────────────────────────


class TestBrowserUI:
    """GET / — browseable Pokedex UI."""

    async def test_index_renders_html(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "<html>" in response.text
            assert "Pokedex" in response.text

    async def test_index_shows_pokemon_cards(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert "pikachu" in response.text.lower()
            assert "charizard" in response.text.lower()

    async def test_type_filter(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/?type=fire")
            assert response.status == 200
            assert "charmander" in response.text.lower()
            # Water types should not appear
            assert "squirtle" not in response.text.lower()

    async def test_search(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/?q=pika")
            assert response.status == 200
            assert "pikachu" in response.text.lower()

    async def test_pagination(self, example_app) -> None:
        async with TestClient(example_app) as client:
            page1 = await client.get("/")
            page2 = await client.get("/?page=2")
            # Different content on different pages
            assert page1.text != page2.text

    async def test_fragment_request(self, example_app) -> None:
        """HX-Request should return just the grid fragment."""
        async with TestClient(example_app) as client:
            response = await client.fragment("/")
            assert response.status == 200
            # Fragment should have card content but not full page shell
            assert "pokemon-grid" in response.text or "card" in response.text

    async def test_detail_page(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/pokemon/25")
            assert response.status == 200
            assert "pikachu" in response.text.lower()
            assert "electric" in response.text.lower()

    async def test_detail_not_found(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/pokemon/99999")
            assert response.status == 404

    async def test_no_auth_needed_for_ui(self, example_app) -> None:
        """Browser routes should not require API key."""
        async with TestClient(example_app) as client:
            response = await client.get("/")
            assert response.status == 200


# ── JSON API ─────────────────────────────────────────────────────────────


class TestHealth:
    """GET /api/health — unauthenticated."""

    async def test_health_no_auth_required(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/api/health")
            assert response.status == 200
            data = response.json
            assert data["status"] == "ok"
            assert data["service"] == "pokedex"


class TestAuthentication:
    """API key middleware."""

    async def test_missing_key_returns_401(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/api/pokemon")
            assert response.status == 401
            assert "Missing" in response.json["error"]

    async def test_invalid_key_returns_401(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/api/pokemon", headers=_BAD_AUTH)
            assert response.status == 401
            assert "Invalid" in response.json["error"]

    async def test_valid_key_succeeds(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/api/pokemon", headers=_AUTH)
            assert response.status == 200


class TestListPokemon:
    """GET /api/pokemon — list with pagination and filters."""

    async def test_returns_paginated_list(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/api/pokemon", headers=_AUTH)
            assert response.status == 200
            data = response.json
            assert "data" in data
            assert "meta" in data
            assert data["meta"]["page"] == 1
            assert data["meta"]["per_page"] == 20

    async def test_pagination_meta(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/api/pokemon?per_page=5&page=1", headers=_AUTH)
            data = response.json
            assert len(data["data"]) == 5
            assert data["meta"]["per_page"] == 5
            assert data["meta"]["total"] == 36
            assert data["meta"]["pages"] == 8

    async def test_page_2(self, example_app) -> None:
        async with TestClient(example_app) as client:
            page1 = await client.get("/api/pokemon?per_page=5&page=1", headers=_AUTH)
            page2 = await client.get("/api/pokemon?per_page=5&page=2", headers=_AUTH)
            ids1 = [p["id"] for p in page1.json["data"]]
            ids2 = [p["id"] for p in page2.json["data"]]
            assert set(ids1).isdisjoint(set(ids2))

    async def test_filter_by_type(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/api/pokemon?type=fire", headers=_AUTH)
            data = response.json
            for pokemon in data["data"]:
                assert "fire" in pokemon["types"]

    async def test_search_by_name(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/api/pokemon?q=char", headers=_AUTH)
            data = response.json
            for pokemon in data["data"]:
                assert "char" in pokemon["name"]

    async def test_combined_filter_and_search(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/api/pokemon?type=fire&q=char", headers=_AUTH)
            data = response.json
            for pokemon in data["data"]:
                assert "fire" in pokemon["types"]
                assert "char" in pokemon["name"]

    async def test_per_page_capped_at_100(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/api/pokemon?per_page=500", headers=_AUTH)
            assert response.json["meta"]["per_page"] == 100

    async def test_types_returned_as_list(self, example_app) -> None:
        """Types field should be a list, not a comma-separated string."""
        async with TestClient(example_app) as client:
            response = await client.get("/api/pokemon?per_page=1", headers=_AUTH)
            pokemon = response.json["data"][0]
            assert isinstance(pokemon["types"], list)

    async def test_legendary_returned_as_bool(self, example_app) -> None:
        """Legendary field should be a boolean, not an integer."""
        async with TestClient(example_app) as client:
            response = await client.get("/api/pokemon?per_page=50", headers=_AUTH)
            for pokemon in response.json["data"]:
                assert isinstance(pokemon["legendary"], bool)


class TestGetPokemon:
    """GET /api/pokemon/{id} — single Pokemon."""

    async def test_get_pikachu(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/api/pokemon/25", headers=_AUTH)
            assert response.status == 200
            pokemon = response.json["data"]
            assert pokemon["name"] == "pikachu"
            assert "electric" in pokemon["types"]

    async def test_not_found(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/api/pokemon/99999", headers=_AUTH)
            assert response.status == 404
            assert "not found" in response.json["error"].lower()


class TestTypes:
    """GET /api/types — distinct type list."""

    async def test_returns_sorted_types(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/api/types", headers=_AUTH)
            assert response.status == 200
            types = response.json["data"]
            assert isinstance(types, list)
            assert "fire" in types
            assert "water" in types
            assert "electric" in types
            assert types == sorted(types)


class TestStats:
    """GET /api/stats — aggregate statistics."""

    async def test_returns_stats(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/api/stats", headers=_AUTH)
            assert response.status == 200
            data = response.json["data"]
            assert data["total"] == 36
            assert data["legendary_count"] > 0
            assert "averages" in data
            assert "types" in data
            assert data["averages"]["hp"] > 0
