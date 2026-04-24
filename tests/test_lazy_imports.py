"""Tests for chirp.__init__ — lazy import registry covers all public names."""

import pytest

import chirp

EXPECTED_PUBLIC_API = [
    "CHIRP_CAPABILITIES",
    "CHIRP_DEFER_PENDING_KEY",
    "DEFERRED",
    "OOB",
    "STOP_POLLING",
    "Action",
    "AnyResponse",
    "App",
    "AppConfig",
    "BlockRef",
    "ChangeEvent",
    "CheckResult",
    "ChirpError",
    "ChirpPlugin",
    "ConfigurationError",
    "ContractCheck",
    "ContractCheckSnapshot",
    "ContractIssue",
    "DependencyIndex",
    "EventStream",
    "FormAction",
    "FormBindingError",
    "Fragment",
    "HTTPError",
    "HtmxDetails",
    "InlineTemplate",
    "MarkdownRenderer",
    "MethodNotAllowed",
    "Middleware",
    "MutationResult",
    "Next",
    "NotFound",
    "Page",
    "PageComposition",
    "ReactiveBus",
    "Redirect",
    "RegionUpdate",
    "RenderPlan",
    "Request",
    "Response",
    "SSEEvent",
    "Severity",
    "ShellAction",
    "ShellActionZone",
    "ShellActions",
    "ShellMenuItem",
    "ShellSubmitSurface",
    "Stream",
    "Suspense",
    "SwapResolution",
    "Template",
    "TemplateStream",
    "ToolCallEvent",
    "ToolDef",
    "ToolEventBus",
    "ToolRegistry",
    "ValidationError",
    "ViewRef",
    "cache_view",
    "form_from",
    "form_or_errors",
    "form_values",
    "g",
    "get_cache",
    "get_render_plan",
    "get_request",
    "get_user",
    "hx_redirect",
    "is_safe_url",
    "login",
    "login_required",
    "logout",
    "reactive_stream",
    "requires",
    "resolve_navigation_swap",
    "use_chirp_ui",
]


@pytest.mark.parametrize("name", chirp.__all__)
def test_all_names_resolve(name: str) -> None:
    """Every name in __all__ must resolve via __getattr__ without error."""
    obj = getattr(chirp, name)
    assert obj is not None, f"chirp.{name} resolved to None"


def test_all_names_in_lazy_registry() -> None:
    """Every name in __all__ has a corresponding entry in _LAZY_IMPORTS."""
    missing = set(chirp.__all__) - set(chirp._LAZY_IMPORTS)
    assert not missing, (
        f"Names in __all__ but not in _LAZY_IMPORTS: {sorted(missing)}. "
        f"Add them to _LAZY_IMPORTS in chirp/__init__.py."
    )


def test_lazy_registry_no_extras() -> None:
    """Every name in _LAZY_IMPORTS should be in __all__ (public API contract)."""
    extras = set(chirp._LAZY_IMPORTS) - set(chirp.__all__)
    assert not extras, (
        f"Names in _LAZY_IMPORTS but not in __all__: {sorted(extras)}. "
        f"Either add them to __all__ or remove from _LAZY_IMPORTS."
    )


def test_unknown_name_raises_attribute_error() -> None:
    """Accessing an unregistered name raises AttributeError."""
    with pytest.raises(AttributeError, match="no attribute"):
        chirp.__getattr__("ThisDoesNotExist")


def test_public_api_snapshot() -> None:
    """Top-level imports should change deliberately, not by accident."""
    assert chirp.__all__ == EXPECTED_PUBLIC_API


def test_public_api_status_covers_all_exports() -> None:
    """Every public export has an explicit stability classification."""
    assert set(chirp._API_STATUS) == set(chirp.__all__)
    assert set(chirp._API_STATUS.values()) == {"debug", "provisional", "stable"}
