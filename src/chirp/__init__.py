"""Chirp — A Python web framework for the modern web platform.

Serves HTML beautifully: full pages, fragments, streams, and real-time events.
Built for Python 3.14t with free-threading support.

Basic usage::

    from chirp import App

    app = App()

    @app.route("/")
    def index():
        return "Hello, World!"

    app.run()

Data access (``pip install chirp[data]``)::

    from chirp.data import Database
    db = Database("sqlite:///app.db")
    users = await db.fetch(User, "SELECT * FROM users")

AI streaming (``pip install chirp[ai]``)::

    from chirp.ai import LLM
    llm = LLM("anthropic:claude-sonnet-4-20250514")
    async for token in llm.stream("Explain:"):
        ...
"""

# Declare free-threading support (PEP 703)
_Py_mod_gil = 0


def _get_version() -> str:
    """Single source of truth: pyproject.toml via package metadata."""
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("bengal-chirp")
    except PackageNotFoundError:
        import tomllib
        from pathlib import Path

        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        if pyproject.exists():
            with open(pyproject, "rb") as f:
                try:
                    return tomllib.load(f)["project"]["version"]
                except KeyError:
                    return "0.0.0.dev"
        return "0.0.0.dev"


__version__ = _get_version()
CHIRP_CAPABILITIES = frozenset(
    {
        # Guarantees startup contract checks run after runtime state publication.
        "contract_checks_runtime_ready",
    }
)

# Public API stability registry. Private so documenting the API does not itself
# widen the top-level import surface.
_API_STATUS: dict[str, str] = {
    # Stable core
    "App": "stable",
    "AppConfig": "stable",
    "Request": "stable",
    "Response": "stable",
    "Redirect": "stable",
    "Template": "stable",
    "InlineTemplate": "stable",
    "Fragment": "stable",
    "Page": "stable",
    "OOB": "stable",
    "EventStream": "stable",
    "SSEEvent": "stable",
    "Stream": "stable",
    "Suspense": "stable",
    "TemplateStream": "stable",
    "ValidationError": "stable",
    "FormAction": "stable",
    "MutationResult": "stable",
    "Action": "stable",
    "AnyResponse": "stable",
    "Middleware": "stable",
    "Next": "stable",
    "g": "stable",
    "get_request": "stable",
    "hx_redirect": "stable",
    "ChirpError": "stable",
    "ConfigurationError": "stable",
    "HTTPError": "stable",
    "MethodNotAllowed": "stable",
    "NotFound": "stable",
    "form_from": "stable",
    "form_or_errors": "stable",
    "form_values": "stable",
    "FormBindingError": "stable",
    "get_user": "stable",
    "login": "stable",
    "logout": "stable",
    "login_required": "stable",
    "requires": "stable",
    "is_safe_url": "stable",
    "MarkdownRenderer": "stable",
    # Provisional extension surfaces
    "CHIRP_CAPABILITIES": "provisional",
    "CHIRP_DEFER_PENDING_KEY": "provisional",
    "DEFERRED": "provisional",
    "STOP_POLLING": "provisional",
    "BlockRef": "provisional",
    "ChangeEvent": "provisional",
    "CheckResult": "provisional",
    "ChirpPlugin": "provisional",
    "ContractCheck": "provisional",
    "ContractCheckSnapshot": "provisional",
    "ContractIssue": "provisional",
    "DependencyIndex": "provisional",
    "DeferredCache": "provisional",
    "HtmxDetails": "provisional",
    "JSONResponse": "stable",
    "ReactiveBus": "provisional",
    "Severity": "provisional",
    "ShellAction": "provisional",
    "ShellActionZone": "provisional",
    "ShellActions": "provisional",
    "ShellMenuItem": "provisional",
    "ShellSubmitSurface": "provisional",
    "ToolCallEvent": "provisional",
    "ToolDef": "provisional",
    "ToolEventBus": "provisional",
    "ToolRegistry": "provisional",
    "cache_view": "provisional",
    "get_cache": "provisional",
    "reactive_stream": "provisional",
    "use_chirp_ui": "provisional",
    # Debug / advanced introspection
    "PageComposition": "debug",
    "RegionUpdate": "debug",
    "RenderPlan": "debug",
    "SwapResolution": "debug",
    "ViewRef": "debug",
    "get_render_plan": "debug",
    "resolve_navigation_swap": "debug",
}

__all__ = [
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
    "DeferredCache",
    "DependencyIndex",
    "EventStream",
    "FormAction",
    "FormBindingError",
    "Fragment",
    "HTTPError",
    "HtmxDetails",
    "InlineTemplate",
    "JSONResponse",
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


# Registry of lazy imports: name -> (module_path, attribute_name).
# Adding a new public name only requires a single line here.
_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    # Application
    "App": ("chirp.app", "App"),
    "CHIRP_CAPABILITIES": ("chirp", "CHIRP_CAPABILITIES"),
    "CHIRP_DEFER_PENDING_KEY": ("chirp.templating.suspense", "CHIRP_DEFER_PENDING_KEY"),
    "DEFERRED": ("chirp.templating.suspense", "DEFERRED"),
    "AppConfig": ("chirp.config", "AppConfig"),
    # Contracts (for plugin authors)
    "ContractCheck": ("chirp.contracts.types", "ContractCheck"),
    "ContractCheckSnapshot": ("chirp.app.state", "ContractCheckSnapshot"),
    "CheckResult": ("chirp.contracts.types", "CheckResult"),
    "ContractIssue": ("chirp.contracts.types", "ContractIssue"),
    "Severity": ("chirp.contracts.types", "Severity"),
    # HTTP
    "HtmxDetails": ("chirp.http.request", "HtmxDetails"),
    "Request": ("chirp.http.request", "Request"),
    "Response": ("chirp.http.response", "Response"),
    "JSONResponse": ("chirp.http.response", "JSONResponse"),
    "Redirect": ("chirp.http.response", "Redirect"),
    "STOP_POLLING": ("chirp.http.response", "STOP_POLLING"),
    "hx_redirect": ("chirp.http.response", "hx_redirect"),
    # Return types
    "Template": ("chirp.templating.returns", "Template"),
    "InlineTemplate": ("chirp.templating.returns", "InlineTemplate"),
    "Fragment": ("chirp.templating.returns", "Fragment"),
    "Page": ("chirp.templating.returns", "Page"),
    "PageComposition": ("chirp.templating.composition", "PageComposition"),
    "RegionUpdate": ("chirp.templating.composition", "RegionUpdate"),
    "ViewRef": ("chirp.templating.composition", "ViewRef"),
    "Action": ("chirp.templating.returns", "Action"),
    "FormAction": ("chirp.templating.returns", "FormAction"),
    "MutationResult": ("chirp.templating.returns", "MutationResult"),
    "Stream": ("chirp.templating.returns", "Stream"),
    "Suspense": ("chirp.templating.returns", "Suspense"),
    "SwapResolution": ("chirp.templating.navigation_swap", "SwapResolution"),
    "resolve_navigation_swap": ("chirp.templating.navigation_swap", "resolve_navigation_swap"),
    "TemplateStream": ("chirp.templating.returns", "TemplateStream"),
    "ValidationError": ("chirp.templating.returns", "ValidationError"),
    "OOB": ("chirp.templating.returns", "OOB"),
    # Realtime
    "EventStream": ("chirp.realtime.events", "EventStream"),
    "SSEEvent": ("chirp.realtime.events", "SSEEvent"),
    # Reactive
    "ReactiveBus": ("chirp.pages.reactive", "ReactiveBus"),
    "DependencyIndex": ("chirp.pages.reactive", "DependencyIndex"),
    "ChangeEvent": ("chirp.pages.reactive", "ChangeEvent"),
    "BlockRef": ("chirp.pages.reactive", "BlockRef"),
    "reactive_stream": ("chirp.pages.reactive.stream", "reactive_stream"),
    "ShellAction": ("chirp.pages.shell_actions", "ShellAction"),
    "ShellActions": ("chirp.pages.shell_actions", "ShellActions"),
    "ShellActionZone": ("chirp.pages.shell_actions", "ShellActionZone"),
    "ShellMenuItem": ("chirp.pages.shell_actions", "ShellMenuItem"),
    "ShellSubmitSurface": ("chirp.pages.shell_actions", "ShellSubmitSurface"),
    # Middleware
    "AnyResponse": ("chirp.middleware.protocol", "AnyResponse"),
    "Middleware": ("chirp.middleware.protocol", "Middleware"),
    "Next": ("chirp.middleware.protocol", "Next"),
    # Context
    "g": ("chirp.context", "g"),
    "get_request": ("chirp.context", "get_request"),
    # Auth
    "get_user": ("chirp.middleware.auth", "get_user"),
    "login": ("chirp.middleware.auth", "login"),
    "logout": ("chirp.middleware.auth", "logout"),
    # Security
    "is_safe_url": ("chirp.security.urls", "is_safe_url"),
    "login_required": ("chirp.security.decorators", "login_required"),
    "requires": ("chirp.security.decorators", "requires"),
    # Errors
    "ChirpError": ("chirp.errors", "ChirpError"),
    "ConfigurationError": ("chirp.errors", "ConfigurationError"),
    "HTTPError": ("chirp.errors", "HTTPError"),
    "MethodNotAllowed": ("chirp.errors", "MethodNotAllowed"),
    "NotFound": ("chirp.errors", "NotFound"),
    # Forms
    "form_from": ("chirp.http.forms", "form_from"),
    "form_or_errors": ("chirp.http.forms", "form_or_errors"),
    "form_values": ("chirp.http.forms", "form_values"),
    "FormBindingError": ("chirp.http.forms", "FormBindingError"),
    # Render introspection
    "RenderPlan": ("chirp.templating.render_plan", "RenderPlan"),
    "get_render_plan": ("chirp.server.debug.render_plan_snapshot", "get_render_plan"),
    # Tools
    "ToolCallEvent": ("chirp.tools.events", "ToolCallEvent"),
    "ToolDef": ("chirp.tools.registry", "ToolDef"),
    "ToolEventBus": ("chirp.tools.events", "ToolEventBus"),
    "ToolRegistry": ("chirp.tools.registry", "ToolRegistry"),
    # Markdown
    "MarkdownRenderer": ("chirp.markdown.renderer", "MarkdownRenderer"),
    # Cache
    "DeferredCache": ("chirp.cache", "DeferredCache"),
    "get_cache": ("chirp.cache", "get_cache"),
    "cache_view": ("chirp.cache", "cache_view"),
    # Plugin
    "ChirpPlugin": ("chirp.plugin", "ChirpPlugin"),
    # Extensions
    "use_chirp_ui": ("chirp.ext.chirp_ui", "use_chirp_ui"),
}


_DEPRECATED_IMPORTS: dict[str, tuple[str, str, str]] = {
    "LayoutPage": (
        "chirp.templating.returns",
        "LayoutPage",
        "LayoutPage is framework-internal and will be removed from the public API. "
        "Import from chirp.templating.returns if needed.",
    ),
}


def __getattr__(name: str) -> object:
    """Lazy imports for public API.

    Keeps ``import chirp`` fast while providing a clean top-level API.
    New names only need a single entry in ``_LAZY_IMPORTS`` above.
    """
    entry = _LAZY_IMPORTS.get(name)
    if entry is not None:
        module_path, attr = entry
        import importlib

        mod = importlib.import_module(module_path)
        return getattr(mod, attr)

    deprecated = _DEPRECATED_IMPORTS.get(name)
    if deprecated is not None:
        import importlib
        import warnings

        module_path, attr, message = deprecated
        warnings.warn(message, DeprecationWarning, stacklevel=2)
        mod = importlib.import_module(module_path)
        return getattr(mod, attr)

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
