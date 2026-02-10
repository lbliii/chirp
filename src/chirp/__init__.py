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
    "OOB",
    "AnyResponse",
    "App",
    "AppConfig",
    "ChirpError",
    "ConfigurationError",
    "EventStream",
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
    "logout",
    "requires",
]


def __getattr__(name: str) -> object:
    """Lazy imports for public API.

    Keeps ``import chirp`` fast while providing a clean top-level API.
    """
    if name == "App":
        from chirp.app import App

        return App

    if name == "AppConfig":
        from chirp.config import AppConfig

        return AppConfig

    if name == "Request":
        from chirp.http.request import Request

        return Request

    if name in ("Response", "Redirect"):
        from chirp.http import response as _resp

        return getattr(_resp, name)

    if name in (
        "Template", "InlineTemplate", "Fragment", "Page", "LayoutPage",
        "Stream", "ValidationError", "OOB",
    ):
        from chirp.templating import returns as _tmpl

        return getattr(_tmpl, name)

    if name in ("EventStream", "SSEEvent"):
        from chirp.realtime import events as _events

        return getattr(_events, name)

    if name in ("AnyResponse", "Middleware", "Next"):
        from chirp.middleware import protocol as _mw

        return getattr(_mw, name)

    if name in ("g", "get_request"):
        from chirp import context as _ctx

        return getattr(_ctx, name)

    if name in ("get_user", "login", "logout"):
        from chirp.middleware import auth as _auth

        return getattr(_auth, name)

    if name == "is_safe_url":
        from chirp.security.urls import is_safe_url

        return is_safe_url

    if name in ("login_required", "requires"):
        from chirp.security import decorators as _decorators

        return getattr(_decorators, name)

    if name in ("ChirpError", "ConfigurationError", "HTTPError", "MethodNotAllowed", "NotFound"):
        from chirp import errors as _errors

        return getattr(_errors, name)

    if name in ("form_from", "form_or_errors", "form_values", "FormBindingError"):
        from chirp.http import forms as _forms

        return getattr(_forms, name)

    if name == "ToolCallEvent":
        from chirp.tools.events import ToolCallEvent

        return ToolCallEvent

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
