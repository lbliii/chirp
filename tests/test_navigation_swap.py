"""Tests for route-aware navigation swap resolution."""

from __future__ import annotations

from chirp.templating.fragment_target_registry import FragmentTargetRegistry
from chirp.templating.navigation_swap import make_swap_attrs


def test_swap_attrs_returns_empty_without_request_context() -> None:
    """swap_attrs must not raise when called outside a request context."""
    fn = make_swap_attrs(
        route_layout_chains={},
        router=None,
        fragment_target_registry=FragmentTargetRegistry(),
        swap_scope_map={},
    )
    assert fn("/some-path") == {}
