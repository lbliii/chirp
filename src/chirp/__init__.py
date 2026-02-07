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

__version__ = "0.1.0-dev"
__all__ = [
    "AnyResponse",
    "App",
    "AppConfig",
    "ChirpError",
    "ConfigurationError",
    "EventStream",
    "Fragment",
    "HTTPError",
    "MethodNotAllowed",
    "Middleware",
    "Next",
    "NotFound",
    "Redirect",
    "Request",
    "Response",
    "SSEEvent",
    "Stream",
    "Template",
    "g",
    "get_request",
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

    if name in ("Template", "Fragment", "Stream"):
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

    if name in ("ChirpError", "ConfigurationError", "HTTPError", "MethodNotAllowed", "NotFound"):
        from chirp import errors as _errors

        return getattr(_errors, name)

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
