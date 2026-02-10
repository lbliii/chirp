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

__version__ = "0.1.0"
__all__ = [
    "Action",
    "OOB",
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
    "MethodNotAllowed",
    "Middleware",
    "Next",
    "NotFound",
    "Page",
    "Redirect",
    "Request",
    "Response",
    "SSEEvent",
    "Stream",
    "Suspense",
    "Template",
    "ToolCallEvent",
    "ValidationError",
    "form_from",
    "form_or_errors",
    "form_values",
    "g",
    "get_request",
    "get_user",
    "login",
    "is_safe_url",
    "login_required",
    "MarkdownRenderer",
    "logout",
    "requires",
]


# Registry of lazy imports: name -> (module_path, attribute_name).
# Adding a new public name only requires a single line here.
_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    # Application
    "App": ("chirp.app", "App"),
    "AppConfig": ("chirp.config", "AppConfig"),
    # HTTP
    "Request": ("chirp.http.request", "Request"),
    "Response": ("chirp.http.response", "Response"),
    "Redirect": ("chirp.http.response", "Redirect"),
    # Return types
    "Template": ("chirp.templating.returns", "Template"),
    "InlineTemplate": ("chirp.templating.returns", "InlineTemplate"),
    "Fragment": ("chirp.templating.returns", "Fragment"),
    "Page": ("chirp.templating.returns", "Page"),
    "LayoutPage": ("chirp.templating.returns", "LayoutPage"),
    "Action": ("chirp.templating.returns", "Action"),
    "FormAction": ("chirp.templating.returns", "FormAction"),
    "Stream": ("chirp.templating.returns", "Stream"),
    "Suspense": ("chirp.templating.returns", "Suspense"),
    "ValidationError": ("chirp.templating.returns", "ValidationError"),
    "OOB": ("chirp.templating.returns", "OOB"),
    # Realtime
    "EventStream": ("chirp.realtime.events", "EventStream"),
    "SSEEvent": ("chirp.realtime.events", "SSEEvent"),
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
