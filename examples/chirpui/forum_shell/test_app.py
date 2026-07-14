"""Tests for the forum_shell ChirpUI example."""

from pathlib import Path

import pytest

from chirp.contracts import check_hypermedia_surface
from chirp.testing import (
    TestClient,
    assert_has_id,
    assert_is_full_page,
    assert_no_full_document,
    assert_oob_targets,
)


class TestForumShell:
    def test_readme_keeps_fixture_boundary_explicit(self) -> None:
        readme = Path(__file__).with_name("README.md").read_text()

        assert "not a full forum product" in readme
        assert "regression fixture" in readme
        assert "general-purpose forum scaffold" in readme

    async def test_boards_page_renders_full_shell(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/boards")
        assert response.status == 200
        assert_is_full_page(response)
        assert "Forum Shell" in response.text
        assert "Boards" in response.text
        assert_has_id(response, "boards-page")

    async def test_boosted_board_page_renders_selectable_shell_outlet(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.fragment(
                "/boards/ic",
                target="main",
                headers={"HX-Boosted": "true"},
            )
        assert response.status == 200
        assert_has_id(response, "page-content")
        assert_has_id(response, "page-root")
        assert "Rain over the night market" in response.text

    async def test_reply_binds_mentions_and_updates_unread_oob(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.post(
                "/boards/ic/threads/market-rain",
                data={
                    "character_id": "2",
                    "body": "Theo steps out of the rain.",
                    "mention_ids": ["1", "3"],
                },
                headers={"HX-Request": "true", "HX-Target": "thread-page"},
            )
        assert response.status == 200
        assert_no_full_document(response)
        assert "Theo steps out of the rain." in response.text
        assert "Mara Vale" in response.text
        assert "Juniper Cross" in response.text
        assert_oob_targets(response, "forum-unread-count")

    async def test_mention_search_returns_json_data_island(self, example_app) -> None:
        async with TestClient(example_app) as client:
            response = await client.get("/mentionables/search", query={"q": "jun"})
        assert response.status == 200
        assert response.content_type == "application/json; charset=utf-8"
        assert response.json == {"items": [{"id": 3, "label": "Juniper Cross", "detail": "Mina"}]}

    def test_example_app_contract_coverage_is_strong(self, example_app) -> None:
        result = check_hypermedia_surface(example_app)
        assert result.ok
        assert result.coverage.post_routes == 1
        assert result.coverage.post_routes_with_form_contract == 1
        assert result.coverage.mounted_page_routes_with_contract >= 1

    @pytest.mark.issue(723)
    def test_enhancement_contracts_remain_declared_only(self, example_app) -> None:
        """No ChirpUI default silently opts the canary into enhancement tiers."""
        example_app.freeze()
        program = example_app._runtime_state.hypermedia_program
        assert program is not None
        assert program.enhancements == ()
        assert program.enhancement_edges == ()
