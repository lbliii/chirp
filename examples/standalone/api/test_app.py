"""Tests for the API example — CRUD, JSON, path params, request body."""

import json

from chirp.testing import TestClient


class TestListItems:
    """GET /api/items — list with limit and offset."""

    async def test_empty_list(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/api/items")
            assert response.status == 200
            data = response.json
            assert data["data"] == []
            assert data["meta"]["total"] == 0

    async def test_list_with_limit_offset(self, example_app) -> None:
        async with TestClient(example_app) as client:
            # Create 3 items
            for i in range(3):
                await client.post("/api/items", json={"title": f"Item {i}"})

            response = await client.get("/api/items?limit=2&offset=1")
            assert response.status == 200
            data = response.json
            assert len(data["data"]) == 2
            assert data["meta"]["limit"] == 2
            assert data["meta"]["offset"] == 1
            assert data["meta"]["total"] == 3


class TestGetItem:
    """GET /api/items/{id} — single item."""

    async def test_get_existing(self, example_app) -> None:
        async with TestClient(example_app) as client:
            create = await client.post("/api/items", json={"title": "Test item"})
            assert create.status == 201
            item_id = create.json["data"]["id"]

            response = await client.get(f"/api/items/{item_id}")
            assert response.status == 200
            assert response.json["data"]["title"] == "Test item"
            assert response.json["data"]["done"] is False

    async def test_get_missing_returns_404(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/api/items/99999")
            assert response.status == 404
            assert "not found" in response.json["error"].lower()


class TestCreateItem:
    """POST /api/items — create."""

    async def test_create_success(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post("/api/items", json={"title": "New item"})
            assert response.status == 201
            data = response.json["data"]
            assert data["title"] == "New item"
            assert data["done"] is False
            assert "id" in data

    async def test_create_missing_title_returns_400(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post("/api/items", json={})
            assert response.status == 400
            assert "title" in response.json["error"].lower()


class TestUpdateItem:
    """PUT /api/items/{id} — update."""

    async def test_update_title(self, example_app) -> None:
        async with TestClient(example_app) as client:
            create = await client.post("/api/items", json={"title": "Original"})
            item_id = create.json["data"]["id"]

            response = await client.put(
                f"/api/items/{item_id}",
                body=json.dumps({"title": "Updated"}).encode(),
                headers={"Content-Type": "application/json"},
            )
            assert response.status == 200
            assert response.json["data"]["title"] == "Updated"

    async def test_update_done(self, example_app) -> None:
        async with TestClient(example_app) as client:
            create = await client.post("/api/items", json={"title": "Task"})
            item_id = create.json["data"]["id"]

            response = await client.put(
                f"/api/items/{item_id}",
                body=json.dumps({"done": True}).encode(),
                headers={"Content-Type": "application/json"},
            )
            assert response.status == 200
            assert response.json["data"]["done"] is True

    async def test_update_missing_returns_404(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.put(
                "/api/items/99999",
                body=json.dumps({"title": "x"}).encode(),
                headers={"Content-Type": "application/json"},
            )
            assert response.status == 404


class TestDeleteItem:
    """DELETE /api/items/{id} — delete."""

    async def test_delete_success(self, example_app) -> None:
        async with TestClient(example_app) as client:
            create = await client.post("/api/items", json={"title": "To delete"})
            item_id = create.json["data"]["id"]

            response = await client.delete(f"/api/items/{item_id}")
            assert response.status == 200
            assert response.json["data"]["id"] == item_id

            get_resp = await client.get(f"/api/items/{item_id}")
            assert get_resp.status == 404

    async def test_delete_missing_returns_404(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.delete("/api/items/99999")
            assert response.status == 404


class TestCRUDFlow:
    """Full CRUD cycle."""

    async def test_create_list_get_update_delete(self, example_app) -> None:
        async with TestClient(example_app) as client:
            # Create
            create = await client.post("/api/items", json={"title": "Flow test"})
            assert create.status == 201
            item_id = create.json["data"]["id"]

            # List
            list_resp = await client.get("/api/items")
            assert list_resp.status == 200
            ids = [i["id"] for i in list_resp.json["data"]]
            assert item_id in ids

            # Get
            get_resp = await client.get(f"/api/items/{item_id}")
            assert get_resp.status == 200
            assert get_resp.json["data"]["title"] == "Flow test"

            # Update
            upd_resp = await client.put(
                f"/api/items/{item_id}",
                body=json.dumps({"title": "Updated", "done": True}).encode(),
                headers={"Content-Type": "application/json"},
            )
            assert upd_resp.status == 200
            assert upd_resp.json["data"]["done"] is True

            # Delete
            del_resp = await client.delete(f"/api/items/{item_id}")
            assert del_resp.status == 200

            # Verify gone
            get_after = await client.get(f"/api/items/{item_id}")
            assert get_after.status == 404
