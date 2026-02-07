"""Request-scoped context via ContextVar.

Provides:
- ``request_var``: The current ``Request`` for this task/thread.
- ``g``: A mutable namespace scoped to the current request.

Both are set by the handler pipeline and reset after each request.
They are explicitly opt-in — if no middleware or handler sets them,
accessing them raises ``LookupError``.

Thread safety:
    ``ContextVar`` is task-local under asyncio and thread-local under
    free-threading (3.14t). No locks needed.
"""

from contextvars import ContextVar
from typing import Any

from chirp.http.request import Request

# -- Request context --

request_var: ContextVar[Request] = ContextVar("chirp_request")
"""The current request. Set by the ASGI handler before dispatch."""


def get_request() -> Request:
    """Return the current request.

    Raises ``LookupError`` if called outside a request context.
    """
    return request_var.get()


# -- Request-scoped namespace --


class _RequestGlobals:
    """A mutable namespace scoped to the current request.

    Inspired by Flask's ``g``. Stores arbitrary attributes via
    a per-request dict held in a ContextVar.

    Usage::

        from chirp.context import g

        # In middleware
        g.user = current_user

        # In handler
        name = g.user.name
    """

    __slots__ = ("_store",)

    def __init__(self) -> None:
        object.__setattr__(self, "_store", ContextVar("chirp_g", default=None))

    def _get_dict(self) -> dict[str, Any]:
        store: ContextVar[dict[str, Any] | None] = object.__getattribute__(self, "_store")
        d = store.get()
        if d is None:
            d = {}
            store.set(d)
        return d

    def __getattr__(self, name: str) -> Any:
        d = self._get_dict()
        try:
            return d[name]
        except KeyError:
            msg = f"'g' has no attribute {name!r} in the current request scope"
            raise AttributeError(msg) from None

    def __setattr__(self, name: str, value: Any) -> None:
        self._get_dict()[name] = value

    def __delattr__(self, name: str) -> None:
        d = self._get_dict()
        try:
            del d[name]
        except KeyError:
            msg = f"'g' has no attribute {name!r} in the current request scope"
            raise AttributeError(msg) from None

    def __contains__(self, name: str) -> bool:
        return name in self._get_dict()

    def get(self, name: str, default: Any = None) -> Any:
        """Get an attribute with a default value."""
        return self._get_dict().get(name, default)

    def __repr__(self) -> str:
        return f"<g {self._get_dict()!r}>"


g = _RequestGlobals()
"""Request-scoped namespace. Stores arbitrary per-request data."""
