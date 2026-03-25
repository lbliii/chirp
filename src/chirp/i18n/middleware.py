"""Locale middleware — detect and set locale per request."""

from contextvars import ContextVar

from chirp.http.request import Request
from chirp.middleware.protocol import AnyResponse, Next

from .detection import detect_from_cookie, detect_from_header, detect_from_url_prefix

_locale_var: ContextVar[str] = ContextVar("chirp_locale")


class LocaleMiddleware:
    """Detect locale from request and set it for the current context.

    Detection order (configurable):
    1. URL prefix (/es/...) — when url_prefix is True
    2. Cookie (chirp_locale)
    3. Accept-Language header
    4. Default locale

    Usage::

        app.add_middleware(LocaleMiddleware(
            supported_locales=("en", "es", "ja"),
            default_locale="en",
        ))
    """

    __slots__ = (
        "_cookie_name",
        "_default",
        "_supported",
        "_url_prefix",
    )

    def __init__(
        self,
        supported_locales: tuple[str, ...] = ("en",),
        default_locale: str = "en",
        cookie_name: str = "chirp_locale",
        url_prefix: bool = False,
    ) -> None:
        self._supported = supported_locales
        self._default = default_locale
        self._cookie_name = cookie_name
        self._url_prefix = url_prefix

    def _detect_locale(self, request: Request) -> str:
        # 1. URL prefix
        if self._url_prefix:
            locale = detect_from_url_prefix(request, self._supported)
            if locale:
                return locale

        # 2. Cookie
        locale = detect_from_cookie(request, self._cookie_name)
        if locale and locale in self._supported:
            return locale

        # 3. Accept-Language header
        locale = detect_from_header(request, self._supported)
        if locale:
            return locale

        # 4. Default
        return self._default

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        locale = self._detect_locale(request)
        token = _locale_var.set(locale)
        try:
            return await next(request)
        finally:
            _locale_var.reset(token)
