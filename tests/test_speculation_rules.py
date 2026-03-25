"""Tests for Speculation Rules injection."""

import json

import pytest

from chirp.server.speculation_rules import (
    build_speculation_rules_json,
    build_speculation_rules_snippet,
    normalize_speculation_rules,
)


class _FakeRoute:
    def __init__(self, path, methods=None, referenced=False):
        self.path = path
        self.methods = frozenset(methods or ["GET"])
        self.referenced = referenced


class _FakeRouter:
    def __init__(self, routes):
        self.routes = routes


class TestNormalize:
    def test_false_is_off(self):
        assert normalize_speculation_rules(False) == "off"

    def test_true_is_conservative(self):
        assert normalize_speculation_rules(True) == "conservative"

    def test_string_modes(self):
        assert normalize_speculation_rules("off") == "off"
        assert normalize_speculation_rules("conservative") == "conservative"
        assert normalize_speculation_rules("moderate") == "moderate"
        assert normalize_speculation_rules("eager") == "eager"

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="Invalid"):
            normalize_speculation_rules("turbo")


class TestBuildRulesJSON:
    def test_off_returns_empty(self):
        router = _FakeRouter([_FakeRoute("/")])
        assert build_speculation_rules_json(router, "off") == ""

    def test_conservative_prefetch_static(self):
        router = _FakeRouter(
            [
                _FakeRoute("/"),
                _FakeRoute("/about"),
                _FakeRoute("/login", methods=["POST"]),
            ]
        )
        result = json.loads(build_speculation_rules_json(router, "conservative"))
        assert "prefetch" in result
        urls = result["prefetch"][0]["urls"]
        assert "/" in urls
        assert "/about" in urls

    def test_post_only_excluded(self):
        router = _FakeRouter(
            [
                _FakeRoute("/"),
                _FakeRoute("/login", methods=["POST"]),
            ]
        )
        result = json.loads(build_speculation_rules_json(router, "conservative"))
        urls = result["prefetch"][0]["urls"]
        assert "/login" not in urls

    def test_sse_routes_excluded(self):
        router = _FakeRouter(
            [
                _FakeRoute("/"),
                _FakeRoute("/events", referenced=True),
            ]
        )
        result = json.loads(build_speculation_rules_json(router, "conservative"))
        urls = result["prefetch"][0]["urls"]
        assert "/events" not in urls

    def test_parametric_routes_become_href_matches(self):
        router = _FakeRouter([_FakeRoute("/users/{id:int}")])
        result = json.loads(build_speculation_rules_json(router, "conservative"))
        prefetch = result["prefetch"][0]
        assert prefetch["source"] == "document"
        assert "/users/*" in prefetch["where"]["or"][0]["href_matches"]

    def test_eager_uses_prerender(self):
        router = _FakeRouter([_FakeRoute("/"), _FakeRoute("/about")])
        result = json.loads(build_speculation_rules_json(router, "eager"))
        assert "prerender" in result
        assert result["prerender"][0]["eagerness"] == "eager"

    def test_moderate_prefetch_and_prerender(self):
        router = _FakeRouter([_FakeRoute("/"), _FakeRoute("/about")])
        result = json.loads(build_speculation_rules_json(router, "moderate"))
        assert "prefetch" in result
        assert "prerender" in result
        assert result["prefetch"][0]["eagerness"] == "eager"
        assert result["prerender"][0]["eagerness"] == "moderate"

    def test_empty_router_returns_empty(self):
        router = _FakeRouter([])
        assert build_speculation_rules_json(router, "conservative") == ""

    def test_no_get_routes_returns_empty(self):
        router = _FakeRouter([_FakeRoute("/submit", methods=["POST"])])
        assert build_speculation_rules_json(router, "conservative") == ""


class TestBuildSnippet:
    def test_off_returns_empty(self):
        router = _FakeRouter([_FakeRoute("/")])
        assert build_speculation_rules_snippet(router, "off") == ""

    def test_snippet_wraps_json(self):
        router = _FakeRouter([_FakeRoute("/"), _FakeRoute("/about")])
        snippet = build_speculation_rules_snippet(router, "conservative")
        assert snippet.startswith('<script type="speculationrules"')
        assert 'data-chirp="speculation-rules"' in snippet
        assert snippet.endswith("</script>")
        assert "/about" in snippet
