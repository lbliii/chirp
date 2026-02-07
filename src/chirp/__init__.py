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
"""

# Declare free-threading support (PEP 703)
_Py_mod_gil = 0

__version__ = "0.1.0-dev"
__all__ = [
    # App
    "App",
    "AppConfig",
    # Real-time
    "EventStream",
    "Fragment",
    # Middleware
    "Middleware",
    "Next",
    "Redirect",
    # HTTP
    "Request",
    "Response",
    "SSEEvent",
    "Stream",
    # Templates
    "Template",
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

    if name in ("Middleware", "Next"):
        from chirp.middleware import protocol as _mw

        return getattr(_mw, name)

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
