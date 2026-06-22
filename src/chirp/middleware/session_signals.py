"""Session-scoped signal SSR seeding middleware.

Seeds the signal registry cache for session-scoped signals on each request and
binds the per-visitor SSE audience key used by ``signal_connect()``.

Requires ``SessionMiddleware`` (for session identity) and should run after
``AuthMiddleware`` when ``require_authenticated=True`` so anonymous visitors
receive global-only bindings.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from chirp.http.request import Request
from chirp.middleware.protocol import AnyResponse, Next
from chirp.realtime.signal_globals import reset_signal_audience, set_signal_audience

SeedFactory = Callable[[], Mapping[str, Any]] | Mapping[str, Callable[[], Any]] | Mapping[str, Any]


def _resolve_seed_value(value: Any) -> Any:
    if callable(value):
        return cast(Callable[[], Any], value)()
    return value


def _resolve_seeds(seeds: SeedFactory) -> dict[str, Any]:
    if isinstance(seeds, Mapping):
        raw = cast(Mapping[str, Any], seeds)
    else:
        raw = cast(Callable[[], Mapping[str, Any]], seeds)()
    return {name: _resolve_seed_value(value) for name, value in raw.items()}


@dataclass(frozen=True, slots=True)
class SessionSignalConfig:
    """Configuration for :class:`SessionSignalMiddleware`."""

    app: Any
    audience_key: Callable[[], str]
    seeds: SeedFactory
    require_authenticated: bool = True
    seed_context: Callable[[], contextlib.AbstractContextManager[Any]] | None = None


class SessionSignalMiddleware:
    """Seed session-scoped signal SSR values and bind the SSE audience key.

    Usage::

        app.add_middleware(SessionSignalMiddleware(SessionSignalConfig(
            app=app,
            audience_key=lambda: session_store.session_key(),
            seeds=lambda: {"balance": load_balance(), "notifications": load_notes()},
        )))
    """

    __slots__ = ("_config",)

    def __init__(self, config: SessionSignalConfig) -> None:
        self._config = config

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        cfg = self._config
        aud = cfg.audience_key()
        token = set_signal_audience(aud)
        try:
            registry = cfg.app._mutable_state.signal_registry
            should_seed = bool(aud) and registry is not None
            if cfg.require_authenticated:
                from chirp.middleware.auth import get_user

                user = get_user()
                if not user.is_authenticated:
                    reset_signal_audience(token)
                    token = set_signal_audience("")
                    should_seed = False
            if should_seed:
                seed_values = _resolve_seeds(cfg.seeds)
                ctx: contextlib.AbstractContextManager[Any] = (
                    cfg.seed_context() if cfg.seed_context is not None else contextlib.nullcontext()
                )
                with ctx:
                    for name, value in seed_values.items():
                        registry.seed(name, value, audience_key=aud)
            return await next(request)
        finally:
            reset_signal_audience(token)
