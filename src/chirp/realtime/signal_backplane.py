"""Private memory/Redis data plane for Chirp signals.

The public signal API stays on :class:`chirp.app.App`; this module owns only
the lifecycle-bound transport selected from ``AppConfig.redis_url``.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import inspect
import threading
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from chirp.errors import ConfigurationError
from chirp.pages.reactive.bus import ReactiveBus
from chirp.pages.reactive.events import ChangeEvent
from chirp.realtime.events import _SignalUpdate


class _SignalBackplaneError(RuntimeError):
    """Fail-loud private transport error without broker-sensitive details."""


@dataclass(frozen=True, slots=True)
class _SignalBackplaneDescriptor:
    backend: Literal["memory", "redis"]
    process_local: bool
    supports_append: bool


@dataclass(frozen=True, slots=True)
class _SignalBackplanePlan:
    descriptor: _SignalBackplaneDescriptor
    redis_url: str | None = field(default=None, repr=False)
    subject_key: bytes | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class _SignalPublication:
    name: str
    subject: str = field(repr=False)
    data: str = field(repr=False)


def compile_signal_backplane_plan(
    *, redis_url: str | None, secret_key: str
) -> _SignalBackplanePlan:
    """Compile the immutable private transport selection without importing Redis."""
    if not redis_url:
        return _SignalBackplanePlan(
            descriptor=_SignalBackplaneDescriptor(
                backend="memory", process_local=True, supports_append=True
            )
        )
    if not secret_key:
        raise ConfigurationError(
            "Redis-backed signals require a shared non-empty AppConfig(secret_key=...) "
            "or CHIRP_SECRET_KEY so every worker derives the same private subjects."
        )
    return _SignalBackplanePlan(
        descriptor=_SignalBackplaneDescriptor(
            backend="redis", process_local=False, supports_append=False
        ),
        redis_url=redis_url,
        subject_key=secret_key.encode("utf-8"),
    )


def signal_subject(
    key: bytes, *, audience: Literal["global", "session"], audience_key: str, name: str
) -> str:
    """Derive the stable opaque Redis subject accepted by RFC 023."""
    message = (
        b"chirp-signal-v1\0"
        + audience.encode("utf-8")
        + b"\0"
        + audience_key.encode("utf-8")
        + b"\0"
        + name.encode("utf-8")
    )
    digest = hmac.new(key, message, hashlib.sha256).digest()
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return f"chirp:signal:v1:{encoded}"


async def _close_resource(resource: Any) -> None:
    close = getattr(resource, "aclose", None) or getattr(resource, "close", None)
    if close is None:
        return
    result = close()
    if inspect.isawaitable(result):
        await result


class _RedisSubscription:
    """One exact-subject subscription owned by its SSE iterator."""

    __slots__ = ("_client", "_closed", "_pubsub")

    def __init__(self, client: Any, pubsub: Any) -> None:
        self._client = client
        self._pubsub = pubsub
        self._closed = False

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await _close_resource(self._pubsub)
        await _close_resource(self._client)


class _SignalBackplaneCoordinator:
    """Lifecycle owner for the private memory-or-Redis signal adapter."""

    __slots__ = (
        "_active",
        "_async_from_url",
        "_bus",
        "_closed",
        "_lock",
        "_plan",
        "_publisher",
        "_started",
    )

    def __init__(self, plan: _SignalBackplanePlan, bus: ReactiveBus) -> None:
        self._plan = plan
        self._bus = bus
        self._lock = threading.Lock()
        self._publisher: Any = None
        self._async_from_url: Any = None
        self._active: set[_RedisSubscription] = set()
        self._started = plan.descriptor.backend == "memory"
        self._closed = False

    @property
    def descriptor(self) -> _SignalBackplaneDescriptor:
        return self._plan.descriptor

    @property
    def distributed(self) -> bool:
        return self._plan.descriptor.backend == "redis"

    async def start(self) -> None:
        if not self.distributed:
            return
        with self._lock:
            if self._started:
                return
            if self._closed:
                raise _SignalBackplaneError(
                    "Redis signal backplane cannot start after it has already closed."
                )
        try:
            import redis
            import redis.asyncio as redis_asyncio
        except ImportError:
            raise ConfigurationError(
                "Redis-backed signals require the optional Redis support. "
                "Install it with `pip install 'chirp[redis]'`."
            ) from None

        publisher: Any = None
        try:
            publisher = redis.from_url(self._plan.redis_url)
            await asyncio.to_thread(publisher.ping)
        except Exception:
            if publisher is not None:
                await _close_resource(publisher)
            raise ConfigurationError(
                "Could not start the Redis signal backplane. Verify CHIRP_REDIS_URL, "
                "Redis availability, and credentials."
            ) from None

        with self._lock:
            if self._closed:
                close_immediately = True
            else:
                self._publisher = publisher
                self._async_from_url = redis_asyncio.from_url
                self._started = True
                close_immediately = False
        if close_immediately:
            await _close_resource(publisher)
            raise _SignalBackplaneError(
                "Redis signal backplane closed before startup could publish its client."
            )

    def publication(
        self,
        *,
        name: str,
        data: str,
        audience: Literal["global", "session"],
        audience_key: str,
    ) -> _SignalPublication:
        if not self.distributed:
            # The memory bus scope is already opaque; it is not exposed to clients.
            from chirp.realtime.signals import _bus_scope

            subject = _bus_scope(name, audience_key)
        else:
            key = self._plan.subject_key
            if key is None:
                raise _SignalBackplaneError(
                    "Redis signal subject key is unavailable during publication planning."
                )
            subject = signal_subject(key, audience=audience, audience_key=audience_key, name=name)
        return _SignalPublication(name=name, subject=subject, data=data)

    def publish(self, publication: _SignalPublication) -> None:
        with self._lock:
            if self._closed:
                raise _SignalBackplaneError(
                    f"Signal backplane is closed for signal {publication.name!r}."
                )
        if not self.distributed:
            self._bus.emit_sync(
                ChangeEvent(
                    scope=publication.subject,
                    changed_paths=frozenset({f"rendered:{publication.name}"}),
                )
            )
            return
        with self._lock:
            publisher = self._publisher
            available = self._started and not self._closed and publisher is not None
        if not available:
            raise _SignalBackplaneError(
                f"Redis signal backplane is unavailable for signal {publication.name!r}."
            )
        try:
            publisher.publish(publication.subject, publication.data.encode("utf-8"))
        except Exception:
            raise _SignalBackplaneError(
                f"Redis signal publish failed for signal {publication.name!r}."
            ) from None

    async def subscribe(self, subjects: Mapping[str, str]) -> AsyncIterator[_SignalUpdate]:
        """Subscribe to exact opaque subjects with one latest slot per subject."""
        if not self.distributed:
            return
        with self._lock:
            from_url = self._async_from_url
            available = self._started and not self._closed and from_url is not None
        if not available:
            raise _SignalBackplaneError(
                "Redis signal backplane is unavailable for a new exact subscription."
            )

        client = from_url(self._plan.redis_url)
        pubsub = client.pubsub()
        subscription = _RedisSubscription(client, pubsub)
        with self._lock:
            if self._closed:
                rejected = True
            else:
                self._active.add(subscription)
                rejected = False
        if rejected:
            await subscription.close()
            raise _SignalBackplaneError(
                "Redis signal backplane closed while creating an exact subscription."
            )

        slots: dict[str, str] = {}
        wake = asyncio.Event()
        reader_error: Exception | None = None

        async def read_messages() -> None:
            nonlocal reader_error
            try:
                await pubsub.subscribe(*subjects)
                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    raw_channel = message.get("channel")
                    channel = (
                        raw_channel.decode("utf-8")
                        if isinstance(raw_channel, bytes)
                        else str(raw_channel)
                    )
                    if channel not in subjects:
                        continue
                    raw_data = message.get("data")
                    data = (
                        raw_data.decode("utf-8") if isinstance(raw_data, bytes) else str(raw_data)
                    )
                    slots[channel] = data
                    wake.set()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                reader_error = exc
            finally:
                wake.set()

        reader = asyncio.create_task(read_messages())
        try:
            while True:
                await wake.wait()
                if slots:
                    subject, data = slots.popitem()
                    if not slots:
                        wake.clear()
                    yield _SignalUpdate(name=subjects[subject], data=data)
                    continue
                if reader.done():
                    if reader_error is not None:
                        raise _SignalBackplaneError(
                            "Redis signal subscription disconnected; reconnect the SSE request."
                        ) from None
                    return
                wake.clear()
        finally:
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)
            await subscription.close()
            with self._lock:
                self._active.discard(subscription)

    async def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            active = tuple(self._active)
            self._active.clear()
            publisher = self._publisher
            self._publisher = None
            self._started = False
        if active:
            await asyncio.gather(*(sub.close() for sub in active), return_exceptions=True)
        self._bus.close()
        if publisher is not None:
            await _close_resource(publisher)
