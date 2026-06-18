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

from contextvars import ContextVar, Token
from typing import Any

from chirp.http.request import Request

# -- Request context --

request_var: ContextVar[Request] = ContextVar("chirp_request")
"""The current request. Set by the ASGI handler before dispatch."""

force_inline_sync_var: ContextVar[bool] = ContextVar("chirp_force_inline_sync", default=False)
"""Pounce sync workers set this so handlers run inline instead of to_thread."""


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

    def _reset(self) -> None:
        """Clear the store for the current context. Called by the handler after each request."""
        store: ContextVar[dict[str, Any] | None] = object.__getattribute__(self, "_store")
        store.set(None)

    def snapshot(self) -> dict[str, Any] | None:
        """Return a shallow copy of the current store, or ``None`` if unused.

        Used to carry request-scoped ``g`` into deferred stream renders
        (``Suspense``, ``Stream``, ``EventStream``) that run after the handler
        ``finally`` has reset the store. Reads the **raw** ContextVar so the
        zero-``g`` hot path allocates nothing: when no handler ever touched
        ``g``, the store is ``None`` and this returns ``None`` (no dict copy).
        """
        store: ContextVar[dict[str, Any] | None] = object.__getattribute__(self, "_store")
        d = store.get()
        if d is None:
            return None
        return dict(d)

    def _restore(self, snap: dict[str, Any] | None) -> Token[dict[str, Any] | None] | None:
        """Install a snapshotted store for the current context.

        Returns a reset token (pass to :meth:`_restore_reset`) or ``None`` when
        there was nothing to restore. Gates on ``is not None`` (not truthiness)
        so an **empty-dict** snapshot still installs a fresh writable store — a
        deferred block can write to ``g`` without crashing.
        """
        if snap is None:
            return None
        store: ContextVar[dict[str, Any] | None] = object.__getattribute__(self, "_store")
        return store.set(dict(snap))

    def _restore_reset(self, token: Token[dict[str, Any] | None] | None) -> None:
        """Reset a store installed by :meth:`_restore`. No-op when *token* is None."""
        if token is None:
            return
        store: ContextVar[dict[str, Any] | None] = object.__getattribute__(self, "_store")
        store.reset(token)

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
