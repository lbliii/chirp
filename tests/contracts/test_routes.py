"""Tests for chirp.contracts.routes — attr_to_method, path_matches_route, decorator."""

from chirp.contracts import (
    FragmentContract,
    RouteContract,
    SSEContract,
    contract,
)
from chirp.contracts.routes import attr_to_method, path_matches_route


class TestAttrToMethod:
    """Map htmx attribute names to HTTP methods."""

    def test_hx_get(self):
        assert attr_to_method("hx-get") == "GET"

    def test_hx_post(self):
        assert attr_to_method("hx-post") == "POST"

    def test_hx_put(self):
        assert attr_to_method("hx-put") == "PUT"

    def test_hx_delete(self):
        assert attr_to_method("hx-delete") == "DELETE"

    def test_hx_patch(self):
        assert attr_to_method("hx-patch") == "PATCH"

    def test_form_action_default(self):
        assert attr_to_method("action") == "GET"

    def test_form_action_get_override(self):
        assert attr_to_method("action", "GET") == "GET"

    def test_form_action_post_override(self):
        assert attr_to_method("action", "POST") == "POST"

    def test_confirm_url_post_override(self):
        assert attr_to_method("confirm_url", "DELETE") == "DELETE"


class TestPathMatchesRoute:
    """Path matching between htmx URLs and route patterns."""

    def test_exact_match(self):
        assert path_matches_route("/api/items", "/api/items")

    def test_no_match(self):
        assert not path_matches_route("/api/items", "/api/users")

    def test_param_match(self):
        assert path_matches_route("/api/items/42", "/api/items/{id}")

    def test_typed_param_match(self):
        assert path_matches_route("/api/items/42", "/api/items/{id:int}")

    def test_multiple_params(self):
        assert path_matches_route("/users/1/posts/5", "/users/{uid}/posts/{pid}")

    def test_different_length(self):
        assert not path_matches_route("/api/items/42/extra", "/api/items/{id}")

    def test_root_path(self):
        assert path_matches_route("/", "/")

    def test_query_string_stripped(self):
        """URLs with query params match route path (htmx hx-get with ?page=1 etc)."""
        assert path_matches_route("/data/table?page=1&sort=name", "/data/table")
        assert path_matches_route("/layout/dir?dir=ltr", "/layout/dir")
        assert path_matches_route("/layout/dir?dir=rtl", "/layout/dir")
        assert path_matches_route("/api/items?filter=active", "/api/items")

    def test_query_string_with_param_route(self):
        """Query string stripped before matching param routes."""
        assert path_matches_route("/api/items/42?expand=details", "/api/items/{id}")


class TestContractDecorator:
    """The @contract decorator attaches metadata to handlers."""

    def test_attaches_contract(self):
        @contract(returns=FragmentContract("search.html", "results"))
        async def handler():
            pass

        assert hasattr(handler, "_chirp_contract")
        rc = handler._chirp_contract
        assert isinstance(rc, RouteContract)
        assert isinstance(rc.returns, FragmentContract)
        assert rc.returns.template == "search.html"
        assert rc.returns.block == "results"

    def test_sse_contract(self):
        @contract(returns=SSEContract(event_types=frozenset({"update", "delete"})))
        async def handler():
            pass

        rc = handler._chirp_contract
        assert isinstance(rc.returns, SSEContract)
        assert "update" in rc.returns.event_types

    def test_description(self):
        @contract(description="Search endpoint")
        async def handler():
            pass

        assert handler._chirp_contract.description == "Search endpoint"
