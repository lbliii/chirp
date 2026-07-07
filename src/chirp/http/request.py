"""Immutable HTTP request.

Frozen metadata with async body access. The request is honest about
what it is: received data that doesn't change.
"""

import re
from collections.abc import AsyncGenerator, Callable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Literal, overload
from urllib.parse import unquote, urlparse

from chirp._internal.asgi import Receive, Scope
from chirp.http.cookies import parse_cookies
from chirp.http.headers import Headers
from chirp.http.query import QueryParams

if TYPE_CHECKING:
    from chirp.http.forms import FormData
    from chirp.middleware.auth import User


_HTMX_TAG_RE = re.compile(r"[A-Za-z][A-Za-z0-9:-]*\Z")


def _valid_htmx_element_id(value: str) -> bool:
    """Return whether *value* is safe to use as a canonical DOM id."""
    if not value or value != value.strip() or "#" in value:
        return False
    return not any(char.isspace() or ord(char) < 0x20 or char in "<>\"'" for char in value)


def _parse_htmx_element_ref(value: str | None) -> tuple[str | None, str | None]:
    """Parse htmx 4 ``tag#id`` metadata without treating selectors as ids."""
    if value is None or value != value.strip() or value.count("#") > 1:
        return None, None
    if "#" not in value:
        return (value, None) if _HTMX_TAG_RE.fullmatch(value) else (None, None)
    tag, element_id = value.split("#", 1)
    if tag and _HTMX_TAG_RE.fullmatch(tag) is None:
        return None, None
    if not _valid_htmx_element_id(element_id):
        return None, None
    return tag or None, element_id


@dataclass(frozen=True, slots=True)
class RequestUrlScope:
    """Request-local public URL prefix.

    Middleware can attach this to a copied ``Request`` when the app routes a
    local path through a tenant or base-path public URL. It applies only to
    app-root paths, leaving external URLs, anchors, and relative paths alone.
    """

    prefix: str = ""

    def __post_init__(self) -> None:
        prefix = self.prefix.strip()
        if not prefix or prefix == "/":
            object.__setattr__(self, "prefix", "")
            return
        if prefix.startswith(("//", "#", "?")) or "://" in prefix:
            msg = "RequestUrlScope.prefix must be an app-root path prefix"
            raise ValueError(msg)
        if not prefix.startswith("/"):
            prefix = f"/{prefix}"
        object.__setattr__(self, "prefix", prefix.rstrip("/"))

    def apply(self, path: str) -> str:
        """Return ``path`` under this request scope when it is app-rooted."""
        if not self.prefix:
            return path
        if not path.startswith("/") or path.startswith(("//", "#", "?")):
            return path
        if path == self.prefix or path.startswith(f"{self.prefix}/"):
            return path
        if path.startswith((f"{self.prefix}?", f"{self.prefix}#")):
            return path
        if path == "/":
            return self.prefix
        if path.startswith(("/?", "/#")):
            return f"{self.prefix}{path[1:]}"
        return f"{self.prefix}{path}"


class HtmxDetails:
    """Parsed htmx request headers with caching.

    Attached to ``request.htmx``. Truthy when ``HX-Request`` is present,
    providing typed access to all htmx request headers. Values are
    computed once and cached for the lifetime of the request.
    """

    __slots__ = ("_cache", "_headers", "_server")

    _headers: Headers
    _server: tuple[str, int] | None
    _cache: dict[str, str | None]

    def __init__(self, headers: Headers, server: tuple[str, int] | None) -> None:
        self._headers = headers
        self._server = server
        self._cache = {}

    def __bool__(self) -> bool:
        """True if this is an htmx request (HX-Request header is present)."""
        return self._headers.get("hx-request") == "true"

    def _get(self, name: str) -> str | None:
        """Read an htmx header with URI-AutoEncoded decoding and caching."""
        if name in self._cache:
            return self._cache[name]
        value = self._headers.get(name)
        if value is None:
            self._cache[name] = None
            return None
        if self._headers.get(f"{name}-uri-autoencoded") == "true":
            value = unquote(value)
        self._cache[name] = value
        return value

    @property
    def boosted(self) -> bool:
        """True if this request came from an hx-boost enhanced element."""
        return self._headers.get("hx-boosted") == "true"

    @property
    def history_restore(self) -> bool:
        """True if htmx is restoring from history (cache miss on back/forward)."""
        return self._headers.get("hx-history-restore-request") == "true"

    @property
    def target(self) -> str | None:
        """The target element ID from HX-Target header."""
        return self._get("hx-target")

    @property
    def target_id(self) -> str | None:
        """HX-Target normalized to a bare DOM id.

        Accepts htmx 4 ``tag#id``, htmx 2 ``#id``, and legacy bare ``id``.
        Selector-like, malformed, and htmx 4 tag-only values return ``None``.
        """
        raw = self.target
        if raw is None:
            return None
        _tag, element_id = _parse_htmx_element_ref(raw)
        if "#" in raw:
            return element_id
        if self._get("hx-request-type") is not None:
            return None
        return raw if _valid_htmx_element_id(raw) else None

    @property
    def target_tag(self) -> str | None:
        """The htmx 4 target tag parsed from ``HX-Target`` when present."""
        raw = self.target
        if raw is None:
            return None
        tag, _element_id = _parse_htmx_element_ref(raw)
        if "#" in raw or self._get("hx-request-type") is not None:
            return tag
        return None

    @property
    def source(self) -> str | None:
        """Raw htmx 4 ``HX-Source`` element metadata."""
        return self._get("hx-source")

    @property
    def source_id(self) -> str | None:
        """The source element id parsed from htmx 4 ``HX-Source``."""
        _tag, element_id = _parse_htmx_element_ref(self.source)
        return element_id

    @property
    def source_tag(self) -> str | None:
        """The source element tag parsed from htmx 4 ``HX-Source``."""
        tag, _element_id = _parse_htmx_element_ref(self.source)
        return tag

    @property
    def trigger(self) -> str | None:
        """The source id from htmx 2 ``HX-Trigger`` or htmx 4 ``HX-Source``."""
        legacy = self._get("hx-trigger")
        return legacy if legacy is not None else self.source_id

    @property
    def trigger_name(self) -> str | None:
        """The name attribute of the trigger element (HX-Trigger-Name header)."""
        return self._get("hx-trigger-name")

    @property
    def current_url(self) -> str | None:
        """The browser's current URL from HX-Current-URL header."""
        return self._get("hx-current-url")

    @property
    def current_url_abs_path(self) -> str | None:
        """The path portion of the browser's current URL.

        Strips scheme and host when the origin matches this request's
        server, returning just the path (+ query + fragment). Returns
        the full URL unchanged when the origin differs or server info
        is unavailable.
        """
        key = "_current_url_abs_path"
        if key in self._cache:
            return self._cache[key]
        url = self.current_url
        if url is None:
            self._cache[key] = None
            return None
        parsed = urlparse(url)
        server = self._server
        if server is not None:
            host, port = server
            request_host = f"{host}:{port}" if port not in (80, 443) else host
            if parsed.netloc == request_host:
                path = parsed.path
                if parsed.query:
                    path = f"{path}?{parsed.query}"
                if parsed.fragment:
                    path = f"{path}#{parsed.fragment}"
                self._cache[key] = path
                return path
        self._cache[key] = url
        return url

    @property
    def prompt(self) -> str | None:
        """The user response to hx-prompt (HX-Prompt header)."""
        return self._get("hx-prompt")

    @property
    def partial(self) -> str | None:
        """The partial element name from HX-Partial header (htmx 4.0+).

        Set when the request originates from an ``<htmx-partial>`` element.
        """
        return self._get("hx-partial")

    @property
    def request_type(self) -> Literal["full", "partial"] | None:
        """Normalized htmx 4 ``HX-Request-Type`` (``full`` or ``partial``)."""
        value = self._get("hx-request-type")
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized == "full":
            return "full"
        if normalized == "partial":
            return "partial"
        return None


class _LazyQueryParams(Mapping[str, str]):
    """QueryParams that parses on first access."""

    __slots__ = ("_parsed", "_raw")

    def __init__(self, raw: bytes) -> None:
        object.__setattr__(self, "_raw", raw)
        object.__setattr__(self, "_parsed", None)

    def _ensure(self) -> QueryParams:
        parsed = object.__getattribute__(self, "_parsed")
        if parsed is None:
            parsed = QueryParams(object.__getattribute__(self, "_raw"))
            object.__setattr__(self, "_parsed", parsed)
        return parsed

    def __getitem__(self, key: str) -> str:
        return self._ensure()[key]

    def __contains__(self, key: object) -> bool:
        return key in self._ensure()

    def __iter__(self) -> Iterator[str]:
        return iter(self._ensure())

    def __len__(self) -> int:
        return len(self._ensure())

    @overload
    def get(self, key: str, default: None = None) -> str | None: ...

    @overload
    def get[T](self, key: str, default: T) -> str | T: ...

    def get(self, key: str, default: object = None) -> object:
        return self._ensure().get(key, default)

    def get_list(self, key: str) -> list[str]:
        return self._ensure().get_list(key)

    def get_int(self, key: str, default: int | None = None) -> int | None:
        return self._ensure().get_int(key, default)

    def get_bool(self, key: str, default: bool | None = None) -> bool | None:
        return self._ensure().get_bool(key, default)


class _LazyCookies(Mapping[str, str]):
    """Cookies that parse on first access."""

    __slots__ = ("_cookie_header", "_parsed")

    def __init__(self, cookie_header: str) -> None:
        object.__setattr__(self, "_cookie_header", cookie_header)
        object.__setattr__(self, "_parsed", None)

    def _ensure(self) -> dict[str, str]:
        parsed = object.__getattribute__(self, "_parsed")
        if parsed is None:
            parsed = parse_cookies(object.__getattribute__(self, "_cookie_header"))
            object.__setattr__(self, "_parsed", parsed)
        return parsed

    def __getitem__(self, key: str) -> str:
        return self._ensure()[key]

    def __contains__(self, key: object) -> bool:
        return key in self._ensure()

    def __iter__(self) -> Iterator[str]:
        return iter(self._ensure())

    def __len__(self) -> int:
        return len(self._ensure())

    @overload
    def get(self, key: str, default: None = None) -> str | None: ...

    @overload
    def get[T](self, key: str, default: T) -> str | T: ...

    def get(self, key: str, default: object = None) -> object:
        return self._ensure().get(key, default)


@dataclass(frozen=True, slots=True)
class Request:
    """An immutable HTTP request.

    Metadata (method, path, headers, etc.) is frozen at creation.
    Body is accessed asynchronously via ``.body()``, ``.json()``, ``.form()``.

    Query params and cookies are parsed lazily on first access (not at creation).

    Request-scoped auth and session accessors are deliberately asymmetric,
    mirroring their underlying primitives:

    - ``request.user`` **never raises** — returns ``AnonymousUser`` when
      ``AuthMiddleware`` is absent or the request is anonymous (mirrors
      ``chirp.middleware.auth.current_user``).
    - ``request.session`` **raises ``LookupError``** when ``SessionMiddleware``
      is absent (mirrors ``chirp.middleware.sessions.get_session``). It does not
      return ``None``, so ``request.session.get("x")`` is the ergonomic, and a
      missing-middleware misconfiguration fails loud rather than silently
      reading from a non-existent session.
    """

    method: str
    path: str
    headers: Headers
    query: QueryParams | _LazyQueryParams
    path_params: dict[str, str]
    http_version: str
    server: tuple[str, int] | None
    client: tuple[str, int] | None
    cookies: Mapping[str, str] | _LazyCookies
    request_id: str  # X-Request-ID from header or generated UUID

    # Private: ASGI receive callable for body streaming
    _receive: Receive

    url_scope: RequestUrlScope | None = None

    # Private: request-bound route reversal; set by the app/server layer
    _url_for: Callable[..., str] | None = field(default=None, repr=False, compare=False)

    # Private: upload/body limits threaded from AppConfig by the handler.
    # Defaults are unbounded/sane so direct construction (tests) is unaffected.
    # _max_request_body_size is the GENERAL body cap (every content type),
    # enforced in stream(); _max_upload_size is the MULTIPART-total cap,
    # enforced by the multipart parser via form().
    _max_request_body_size: int | None = field(default=None, repr=False, compare=False)
    _max_upload_size: int | None = field(default=None, repr=False, compare=False)
    _upload_spool_threshold: int | None = field(default=None, repr=False, compare=False)
    _max_upload_parts: int | None = field(default=None, repr=False, compare=False)

    # Private: mutable cache for body and parsed form data
    # (dict contents are mutable even though the field reference is frozen)
    _cache: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    # -- Computed properties --

    @property
    def htmx(self) -> HtmxDetails:
        """Typed, cached htmx request details.

        Truthy when ``HX-Request`` is present::

            if request.htmx:
                target = request.htmx.target
        """
        if "_htmx" not in self._cache:
            self._cache["_htmx"] = HtmxDetails(self.headers, self.server)
        return self._cache["_htmx"]

    @property
    def user(self) -> User:
        """The current authenticated user, or ``AnonymousUser``.

        Never raises: returns ``AnonymousUser`` when ``AuthMiddleware`` is
        absent or the request is anonymous. Mirrors
        ``chirp.middleware.auth.current_user``::

            if request.user.is_authenticated:
                greet(request.user.id)
        """
        # Lazy import: chirp.middleware.auth imports chirp.http.request, so a
        # module-level import here would create a cycle.
        from chirp.middleware.auth import current_user

        return current_user()

    @property
    def trusted_client_ip(self) -> str:
        """The trusted-proxy-corrected client IP — the blessed accessor for
        rate limiting and audit keying.

        Returns ``client[0]`` (the source IP for the TCP peer), falling back to
        ``"unknown"`` when the ASGI scope carries no client. **Never raises.**

        This is fail-closed: it deliberately does **not** read a raw
        ``X-Forwarded-For`` header, which is client-controlled and trivially
        spoofable. In production Chirp's ASGI server (pounce) applies the
        trusted-proxy model (``trusted_proxies`` + ``forwarded_for_trusted_hops``)
        and writes the corrected client into ``scope["client"]`` **before**
        Chirp builds this ``Request`` — so ``client[0]`` is already the
        trusted-derived IP. Under the dev/run path and ``TestClient``, the
        forwarded-for logic is not run, so an attacker-supplied
        ``X-Forwarded-For`` is correctly ignored here.

        Caveat: under a non-pounce ASGI server that leaves ``scope["client"]``
        as the raw socket peer without applying a trusted-proxy model, this is
        only as trustworthy as that server's handling of the proxy chain.
        """
        client = self.client
        if client:
            return client[0]
        return "unknown"

    @property
    def session(self) -> dict[str, Any]:
        """The request-scoped session dict.

        Raises ``LookupError`` when ``SessionMiddleware`` is absent — this
        fail-loud contract mirrors ``chirp.middleware.sessions.get_session``
        (it never returns ``None``)::

            request.session["cart"] = items
            count = request.session.get("count", 0)
        """
        # Lazy import: avoid an import cycle (sessions imports request).
        from chirp.middleware.sessions import get_session

        return get_session()

    def with_url_scope(self, scope: RequestUrlScope | str | None) -> Request:
        """Return a copy of this request with a public URL scope attached."""
        if scope is None:
            url_scope = None
        elif isinstance(scope, RequestUrlScope):
            url_scope = scope
        else:
            url_scope = RequestUrlScope(scope)
        return replace(self, url_scope=url_scope)

    def scoped_url(self, path: str) -> str:
        """Apply the request URL scope to an app-root path."""
        if self.url_scope is None:
            return path
        return self.url_scope.apply(path)

    def url_for(self, name: str, /, **params: Any) -> str:
        """Reverse a named route and apply this request's URL scope."""
        if self._url_for is None:
            msg = "request.url_for() requires a Chirp request created by the app/server pipeline"
            raise RuntimeError(msg)
        return self.scoped_url(self._url_for(name, **params))

    # -- Convenience aliases (delegate to request.htmx) --

    @property
    def is_htmx(self) -> bool:
        """True if this is any htmx request (HX-Request header present)."""
        return bool(self.htmx)

    @property
    def is_narrow_fragment(self) -> bool:
        """True if this htmx request targets a narrow fragment swap.

        False for boosted navigations and history restores, which need
        full page content despite using htmx transport.
        """
        if not self.htmx or self.htmx.boosted or self.htmx.history_restore:
            return False
        if self.htmx.request_type == "full":
            raw_target = self.htmx.target
            if raw_target is None:
                return False
            if raw_target.lower() in {"body", "html"}:
                return False
            if self.htmx.target_tag in {"body", "html"}:
                return False
        return True

    @property
    def is_fragment(self) -> bool:
        """True if this is an htmx request (HX-Request header).

        .. deprecated::
            Use ``is_htmx`` (any htmx request) or ``is_narrow_fragment``
            (narrow fragment swap, excludes boosted and history restore).
        """
        import warnings

        warnings.warn(
            "request.is_fragment is ambiguous for boosted navigations. "
            "Use request.is_htmx (any htmx) or request.is_narrow_fragment "
            "(narrow swap only).",
            DeprecationWarning,
            stacklevel=2,
        )
        return bool(self.htmx)

    @property
    def is_history_restore(self) -> bool:
        """True if htmx is restoring from history (cache miss on back/forward)."""
        return self.htmx.history_restore

    @property
    def is_boosted(self) -> bool:
        """True if this request came from an hx-boost enhanced element."""
        return self.htmx.boosted

    @property
    def htmx_target(self) -> str | None:
        """The target element ID from HX-Target header."""
        return self.htmx.target

    @property
    def htmx_target_id(self) -> str | None:
        """HX-Target normalized to a bare DOM id (no leading ``#``).

        Canonical form used throughout the framework's request → registry
        pipeline. Callers should prefer this over ``htmx_target`` unless
        they specifically need the raw header value.
        """
        return self.htmx.target_id

    @property
    def htmx_target_tag(self) -> str | None:
        """The htmx 4 target tag parsed from ``HX-Target``."""
        return self.htmx.target_tag

    @property
    def htmx_source(self) -> str | None:
        """Raw htmx 4 ``HX-Source`` element metadata."""
        return self.htmx.source

    @property
    def htmx_source_id(self) -> str | None:
        """The source id parsed from htmx 4 ``HX-Source``."""
        return self.htmx.source_id

    @property
    def htmx_source_tag(self) -> str | None:
        """The source tag parsed from htmx 4 ``HX-Source``."""
        return self.htmx.source_tag

    @property
    def htmx_trigger(self) -> str | None:
        """The htmx 2 trigger id or htmx 4 source id."""
        return self.htmx.trigger

    @property
    def htmx_trigger_name(self) -> str | None:
        """The name attribute of the trigger element (HX-Trigger-Name header)."""
        return self.htmx.trigger_name

    @property
    def htmx_current_url(self) -> str | None:
        """The browser's current URL from HX-Current-URL header."""
        return self.htmx.current_url

    @property
    def htmx_current_url_abs_path(self) -> str | None:
        """The path portion of the browser's current URL."""
        return self.htmx.current_url_abs_path

    @property
    def htmx_partial(self) -> str | None:
        """The partial element name from HX-Partial header (htmx 4.0+)."""
        return self.htmx.partial

    @property
    def htmx_request_type(self) -> Literal["full", "partial"] | None:
        """Normalized htmx 4 ``HX-Request-Type`` value."""
        return self.htmx.request_type

    @property
    def content_type(self) -> str | None:
        """The Content-Type header value."""
        return self.headers.get("content-type")

    @property
    def content_length(self) -> int | None:
        """The Content-Length header as int."""
        value = self.headers.get("content-length")
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    @property
    def url(self) -> str:
        """Full request URL (path + query string)."""
        qs = (
            self.query._raw
            if isinstance(self.query, QueryParams)
            else object.__getattribute__(self.query, "_raw")
        )
        if qs:
            return f"{self.path}?{qs.decode('latin-1')}"
        return self.path

    # -- Async body access --

    async def body(self) -> bytes:
        """Read the full request body.

        Result is cached — the ASGI receive is consumed once, then
        the same bytes are returned on subsequent calls.

        Raises ``PayloadTooLarge`` (413) if the accumulated body exceeds
        ``_max_request_body_size`` before the chunks are joined into RAM. On
        overflow the cache is *not* poisoned with a partial buffer, so the
        read-once guarantee still holds for the (failed) call.
        """
        if "_body" in self._cache:
            return self._cache["_body"]
        chunks = [chunk async for chunk in self.stream()]
        result = b"".join(chunks)
        self._cache["_body"] = result
        return result

    async def stream(self) -> AsyncGenerator[bytes]:
        """Stream the request body in chunks.

        Enforces the general ``_max_request_body_size`` cap (applies to EVERY
        content type — JSON, text, urlencoded, multipart) as bytes arrive: if
        the running total would exceed the limit, raises ``PayloadTooLarge``
        (413) *before* yielding the overflowing chunk — so an oversize body is
        rejected without ever joining the whole body into memory. The
        multipart-specific ``_max_upload_size`` is enforced separately by the
        multipart parser (see ``form()``); this cap is the outer envelope.
        """
        limit = self._max_request_body_size
        total = 0
        while True:
            message = await self._receive()
            body = message.get("body", b"")
            if body:
                if limit is not None:
                    total += len(body)
                    if total > limit:
                        from chirp.errors import PayloadTooLarge

                        # NOTE: raising here leaves the ASGI receive channel
                        # partially consumed — the read-once invariant is not
                        # preserved across a failed-then-retried body()/stream()
                        # call. Moot in practice: an overflowing request is
                        # aborted with a 413 and never read again.
                        raise PayloadTooLarge(
                            f"Request body exceeds the maximum size of {limit} bytes."
                        )
                yield body
            if not message.get("more_body", False):
                break

    async def json(self) -> Any:
        """Parse the body as JSON."""
        import json as json_module

        raw = await self.body()
        return json_module.loads(raw)

    async def text(self) -> str:
        """Read the body as text (UTF-8)."""
        raw = await self.body()
        return raw.decode("utf-8")

    async def form(self) -> FormData:
        """Parse the body as form data (URL-encoded or multipart).

        Result is cached — the body is read and parsed once, then
        the same ``FormData`` is returned on subsequent calls.

        Supports ``application/x-www-form-urlencoded`` (stdlib) and
        ``multipart/form-data`` (requires ``pip install chirp[forms]``).

        Returns:
            Parsed ``FormData`` implementing ``MultiValueMapping``.

        Raises:
            ValueError: If Content-Type is not a form encoding.
            ConfigurationError: If multipart is needed but
                ``python-multipart`` is not installed.
        """
        if "_form" in self._cache:
            return self._cache["_form"]

        from chirp.http.forms import parse_form_data

        ct = self.content_type or "application/x-www-form-urlencoded"
        raw = await self.body()
        result = await parse_form_data(
            raw,
            ct,
            max_parts=self._max_upload_parts,
            max_total_size=self._max_upload_size,
            spool_threshold=self._upload_spool_threshold,
        )

        # Cache in the mutable dict (frozen dataclass allows mutating
        # the dict object itself, just not replacing the field reference)
        self._cache["_form"] = result
        return result

    # -- Factory --

    @classmethod
    def from_asgi(
        cls,
        scope: Scope,
        receive: Receive,
        path_params: dict[str, str] | None = None,
        *,
        url_for: Callable[..., str] | None = None,
        max_request_body_size: int | None = None,
        max_upload_size: int | None = None,
        upload_spool_threshold: int | None = None,
        max_upload_parts: int | None = None,
    ) -> Request:
        """Create a Request from an ASGI scope and receive callable.

        Reuses request_id from scope["extensions"]["request_id"] when Pounce
        (or another ASGI server) has already set it, avoiding redundant UUID generation.
        """
        import uuid

        headers = Headers(tuple(scope.get("headers", ())))
        server = scope.get("server")
        client = scope.get("client")
        extensions = scope.get("extensions") or {}
        request_id = (
            extensions.get("request_id") or headers.get("x-request-id") or str(uuid.uuid4())
        )
        query_raw = scope.get("query_string", b"")
        cookie_header = headers.get("cookie") or ""
        return cls(
            method=scope["method"],
            path=scope["path"],
            headers=headers,
            query=_LazyQueryParams(query_raw),
            path_params=path_params or {},
            http_version=scope.get("http_version", "1.1"),
            server=tuple(server) if server else None,
            client=tuple(client) if client else None,
            cookies=_LazyCookies(cookie_header),
            request_id=request_id,
            _receive=receive,
            _url_for=url_for,
            _max_request_body_size=max_request_body_size,
            _max_upload_size=max_upload_size,
            _upload_spool_threshold=upload_spool_threshold,
            _max_upload_parts=max_upload_parts,
        )
