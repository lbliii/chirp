"""Tests for shell context assembly."""

from unittest.mock import MagicMock

from chirp.pages.shell_context import build_shell_context, resolve_meta
from chirp.pages.types import RouteMeta


def test_build_shell_context_produces_correct_keys() -> None:
    """build_shell_context produces correct keys from RouteMeta + section."""
    request = MagicMock()
    request.path = "/docs/guide"
    meta = RouteMeta(title="Guide", breadcrumb_label="User Guide")
    section_ctx = {
        "tab_items": [{"label": "Guide", "href": "/docs/guide"}],
        "breadcrumb_prefix": [{"label": "Docs", "href": "/docs"}],
    }
    cascade_ctx = {}

    result = build_shell_context(request, meta, section_ctx, cascade_ctx)

    assert result["current_path"] == "/docs/guide"
    assert result["page_title"] == "Guide"
    assert result["breadcrumb_items"] == [
        {"label": "Docs", "href": "/docs"},
        {"label": "User Guide", "href": "/docs/guide"},
    ]
    assert result["tab_items"] == [{"label": "Guide", "href": "/docs/guide"}]


def test_build_shell_context_omits_keys_when_source_none() -> None:
    """build_shell_context omits keys when source is None."""
    request = MagicMock()
    request.path = "/"
    meta = None
    section_ctx = {}
    cascade_ctx = {}

    result = build_shell_context(request, meta, section_ctx, cascade_ctx)

    assert result["current_path"] == "/"
    assert "page_title" not in result
    assert "breadcrumb_items" not in result
    assert "tab_items" not in result


def test_resolve_meta_returns_static_meta() -> None:
    """resolve_meta returns static meta when provided."""
    meta = RouteMeta(title="Static")
    result = resolve_meta(meta, None, {}, {})
    assert result is meta
    assert result.title == "Static"


def test_resolve_meta_returns_none_when_both_absent() -> None:
    """resolve_meta returns None when meta and meta_provider both absent."""
    result = resolve_meta(None, None, {}, {})
    assert result is None


def test_resolve_meta_calls_provider_with_path_params() -> None:
    """resolve_meta calls provider with path params and services."""
    def meta_provider(name: str) -> RouteMeta:
        return RouteMeta(title=f"Skill: {name}")

    result = resolve_meta(
        None, meta_provider, {"name": "foo"}, {}
    )
    assert result is not None
    assert result.title == "Skill: foo"


def test_backward_compat_app_without_meta() -> None:
    """Backward compat: app without _meta.py produces same shell context shape."""
    request = MagicMock()
    request.path = "/"
    meta = None
    section_ctx = {}
    cascade_ctx = {}

    result = build_shell_context(request, meta, section_ctx, cascade_ctx)

    # Only current_path when no meta — minimal additive change
    assert result == {"current_path": "/"}
