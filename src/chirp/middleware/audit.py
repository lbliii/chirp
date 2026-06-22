"""HTTP audit middleware — opt-in per-request who/what/when/status trail.

``AuditMiddleware`` emits one structured event per (audited) request through the
**existing** :func:`chirp.security.audit.emit_security_event` sink, under an
``http.request`` namespace — so general request auditing and auth/CSRF telemetry
flow through one pipeline (one sink, one SIEM forwarder).

It is **opt-in and off by default** (explicit-over-magic, like the auth leg):
nothing is emitted unless ``AuditConfig.level`` is raised above ``"none"``. Wire
it via ``secure_stack(config, audit=AuditConfig(level="metadata"))`` or
``app.add_middleware(AuditMiddleware(AuditConfig(...)))``.

Verbosity is tiered (``NONE`` < ``METADATA`` < ``REQUEST`` < ``REQUEST_RESPONSE``):

- ``none`` — disabled; emit nothing.
- ``metadata`` — who/what/when/status only (method, path, status_code,
  source_ip, user_agent, user_id). No body capture.
- ``request`` — metadata **plus** a byte-capped, redacted snapshot of the
  request body for audited methods.
- ``request_response`` — reserved; treated as ``request`` for body capture
  (response-body capture is intentionally not implemented to avoid buffering
  large/streaming responses).

Hypermedia correctness (the critical safety property): the middleware runs
*after* ``next()`` has resolved the response, then branches on the response
**type**. For ``StreamingResponse`` / ``SSEResponse`` / ``FileResponse``
(Chirp's ``Stream`` / ``Suspense`` / ``EventStream`` return types resolve to
these) it downgrades to **metadata-only** and **never** touches
``request.body()`` / ``request.form()`` — draining a streaming request would
buffer unbounded or break the stream, and a request body already consumed by the
handler is read from cache only when present.

Source IP comes from :attr:`chirp.http.request.Request.trusted_client_ip` — the
trusted-proxy-corrected client, never a re-parsed (spoofable) ``X-Forwarded-For``.

User identity comes from ``request.user.id`` and is only non-anonymous when
``AuthMiddleware`` is wired upstream; without it the trail records an anonymous
user (it never crashes).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode

from chirp.contracts.rules_security_stack import MUTATING_METHODS
from chirp.http.response import FileResponse, SSEResponse, StreamingResponse
from chirp.security.audit import emit_security_event

if TYPE_CHECKING:
    from chirp.http.request import Request
    from chirp.middleware.protocol import AnyResponse, Next

# Tiered verbosity levels, ordered weakest -> strongest.
_LEVEL_NONE = "none"
_LEVEL_METADATA = "metadata"
_LEVEL_REQUEST = "request"
_LEVEL_REQUEST_RESPONSE = "request_response"
_VALID_LEVELS = frozenset({_LEVEL_NONE, _LEVEL_METADATA, _LEVEL_REQUEST, _LEVEL_REQUEST_RESPONSE})

# urlencode-safe sentinel: survives application/x-www-form-urlencoded
# re-encoding without percent-escaping (stays readable in audit logs).
_REDACTED = "REDACTED"


@dataclass(frozen=True, slots=True)
class AuditConfig:
    """Configuration for :class:`AuditMiddleware` (frozen, thread-safe).

    Attributes:
        level: Verbosity. One of ``"none"`` (default, OFF), ``"metadata"``,
            ``"request"``, ``"request_response"``. Anything above ``"none"``
            enables auditing.
        max_body_bytes: Byte cap on captured request body (``request`` /
            ``request_response`` levels only, buffered ``Response`` only).
        audited_methods: HTTP methods that are audited. Defaults to the canonical
            :data:`chirp.contracts.rules_security_stack.MUTATING_METHODS`
            (``POST``/``PUT``/``PATCH``/``DELETE``). Non-audited methods emit
            nothing.
        redact_keys: Form/query keys whose values are masked before capture
            (case-insensitive). Defaults cover ``password``/``token``/``secret``/
            ``csrf_token``.
        redact_patterns: Optional regex patterns; any captured-body substring
            matching a pattern is masked. Applied after key redaction.
    """

    level: str = _LEVEL_NONE
    max_body_bytes: int = 4096
    audited_methods: frozenset[str] = MUTATING_METHODS
    redact_keys: tuple[str, ...] = ("password", "token", "secret", "csrf_token")
    redact_patterns: tuple[str, ...] = ()
    # Precompiled redaction patterns — derived once at construction so the
    # per-request hot path does no recompilation. Excluded from init/compare.
    _compiled_patterns: tuple[re.Pattern[str], ...] = field(
        default=(), init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if self.level not in _VALID_LEVELS:
            raise ValueError(
                f"AuditConfig.level must be one of {sorted(_VALID_LEVELS)}, got {self.level!r}"
            )
        compiled = tuple(re.compile(p) for p in self.redact_patterns)
        # Frozen dataclass: bypass the immutability guard for the derived cache.
        object.__setattr__(self, "_compiled_patterns", compiled)

    @property
    def enabled(self) -> bool:
        """True when auditing is on (level above ``"none"``)."""
        return self.level != _LEVEL_NONE

    @property
    def captures_body(self) -> bool:
        """True when the configured level captures the request body."""
        return self.level in (_LEVEL_REQUEST, _LEVEL_REQUEST_RESPONSE)


class AuditMiddleware:
    """Opt-in per-request audit trail over the security-event sink.

    Usage::

        from chirp.middleware.audit import AuditConfig, AuditMiddleware

        app.add_middleware(AuditMiddleware(AuditConfig(level="metadata")))

    Or as the outermost leg of the secure-by-default stack::

        for mw in secure_stack(app.config, audit=AuditConfig(level="request")):
            app.add_middleware(mw)

    Holds only the immutable :class:`AuditConfig` in ``__slots__`` (no shared
    mutable state); the event sink is lock-guarded in ``chirp.security.audit``.
    """

    __slots__ = ("config",)

    def __init__(self, config: AuditConfig | None = None) -> None:
        self.config = config or AuditConfig()

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        response = await next(request)
        config = self.config
        # Off by default, and only audited methods are trailed.
        if not config.enabled or request.method not in config.audited_methods:
            return response

        details: dict[str, object] = {
            "status_code": _status_of(response),
            "source_ip": request.trusted_client_ip,
            "user_agent": request.headers.get("user-agent"),
        }

        # CRITICAL: branch on response TYPE. Streaming/SSE/file responses
        # (Stream/Suspense/EventStream return types) downgrade to metadata-only
        # and the request body is NEVER drained.
        is_streaming = isinstance(response, (StreamingResponse, SSEResponse, FileResponse))
        if config.captures_body and not is_streaming:
            details["body"] = self._capture_body(request)
        elif is_streaming and config.captures_body:
            # Record why the body was withheld so audit reviewers can tell a
            # streaming downgrade apart from an empty body.
            details["body"] = None
            details["body_omitted"] = "streaming_response"

        emit_security_event(
            "http.request",
            request=request,
            user_id=_user_id_of(request),
            details=details,
        )
        return response

    def _capture_body(self, request: Request) -> str | None:
        """Return a byte-capped, redacted snapshot of the already-read body.

        Reads only the cached body (the handler has already consumed the ASGI
        receive stream by the time this middleware runs); if the body was never
        read it is not drained here — capturing it would mean reading a stream
        that the handler chose not to, which is out of scope for an after-the-fact
        audit trail.
        """
        cached = request._cache.get("_body")
        if cached is None:
            return None
        raw = cached[: self.config.max_body_bytes]
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return f"<{len(cached)} bytes, non-utf8>"
        return self._redact(request, text)

    def _redact(self, request: Request, text: str) -> str:
        """Apply config-driven key and pattern redaction to a captured body."""
        config = self.config
        result = text
        content_type = request.content_type or ""
        if config.redact_keys and content_type.startswith("application/x-www-form-urlencoded"):
            redact_lower = {k.lower() for k in config.redact_keys}
            pairs = parse_qsl(result, keep_blank_values=True)
            result = urlencode(
                [(k, _REDACTED if k.lower() in redact_lower else v) for k, v in pairs]
            )
        for pattern in config._compiled_patterns:
            result = pattern.sub(_REDACTED, result)
        return result


def _status_of(response: AnyResponse) -> int:
    """Best-effort status code for any resolved response type."""
    return getattr(response, "status", 200)


def _user_id_of(request: Request) -> str | None:
    """Resolve the audited user id (anonymous when AuthMiddleware is absent)."""
    user = request.user
    user_id = getattr(user, "id", None)
    return str(user_id) if user_id is not None else None
