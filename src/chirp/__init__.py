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
__all__ = [
    "CHIRP_CAPABILITIES",
    "OOB",
    "STOP_POLLING",
    "Action",
    "AnyResponse",
    "App",
    "AppConfig",
    "ChirpError",
    "ConfigurationError",
    "EventStream",
    "FormAction",
    "FormBindingError",
    "Fragment",
    "HTTPError",
    "InlineTemplate",
    "LayoutPage",
    "MarkdownRenderer",
    "MethodNotAllowed",
    "Middleware",
    "Next",
    "NotFound",
    "Page",
    "PageComposition",
    "Redirect",
    "RegionUpdate",
    "Request",
    "Response",
    "SSEEvent",
    "ShellAction",
    "ShellActionZone",
    "ShellActions",
    "ShellMenuItem",
    "ShellSubmitSurface",
    "Stream",
    "Suspense",
    "Template",
    "TemplateStream",
    "ToolCallEvent",
    "ValidationError",
    "ViewRef",
    "form_from",
    "form_or_errors",
    "form_values",
    "g",
    "get_request",
    "get_user",
    "hx_redirect",
    "is_safe_url",
    "login",
    "login_required",
    "logout",
    "requires",
    "use_chirp_ui",
]


# Registry of lazy imports: name -> (module_path, attribute_name).
# Adding a new public name only requires a single line here.
_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    # Application
    "App": ("chirp.app", "App"),
    "CHIRP_CAPABILITIES": ("chirp", "CHIRP_CAPABILITIES"),
    "AppConfig": ("chirp.config", "AppConfig"),
    # HTTP
    "Request": ("chirp.http.request", "Request"),
    "Response": ("chirp.http.response", "Response"),
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
    "LayoutPage": ("chirp.templating.returns", "LayoutPage"),
    "Action": ("chirp.templating.returns", "Action"),
    "FormAction": ("chirp.templating.returns", "FormAction"),
    "Stream": ("chirp.templating.returns", "Stream"),
    "Suspense": ("chirp.templating.returns", "Suspense"),
    "TemplateStream": ("chirp.templating.returns", "TemplateStream"),
    "ValidationError": ("chirp.templating.returns", "ValidationError"),
    "OOB": ("chirp.templating.returns", "OOB"),
    # Realtime
    "EventStream": ("chirp.realtime.events", "EventStream"),
    "SSEEvent": ("chirp.realtime.events", "SSEEvent"),
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
    # Tools
    "ToolCallEvent": ("chirp.tools.events", "ToolCallEvent"),
    # Markdown
    "MarkdownRenderer": ("chirp.markdown.renderer", "MarkdownRenderer"),
    # Extensions
    "use_chirp_ui": ("chirp.ext.chirp_ui", "use_chirp_ui"),
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
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
