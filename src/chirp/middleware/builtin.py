"""Built-in middleware: CORS.

Provides a standards-compliant CORS middleware that handles
preflight requests and adds appropriate headers to all responses.
"""

from dataclasses import dataclass

from chirp.http.request import Request
from chirp.http.response import Response
from chirp.middleware.protocol import AnyResponse, Next


@dataclass(frozen=True, slots=True)
class CORSConfig:
    """CORS middleware configuration.

    All fields have secure defaults (nothing is allowed).
    Override what you need::

        CORSConfig(
            allow_origins=["https://example.com"],
            allow_methods=["GET", "POST"],
        )
    """

    allow_origins: tuple[str, ...] = ()
    allow_methods: tuple[str, ...] = ("GET", "HEAD", "OPTIONS")
    allow_headers: tuple[str, ...] = ()
    expose_headers: tuple[str, ...] = ()
    allow_credentials: bool = False
    max_age: int = 600  # 10 minutes


class CORSMiddleware:
    """Standards-compliant CORS middleware.

    Handles:
    - Preflight ``OPTIONS`` requests (returns 204 with CORS headers)
    - Simple and actual requests (adds CORS headers to response)
    - Credential support (``Access-Control-Allow-Credentials``)
    - Wildcard origins (``"*"``) when credentials are disabled

    Usage::

        app.add_middleware(CORSMiddleware(CORSConfig(
            allow_origins=["https://example.com"],
            allow_methods=["GET", "POST", "PUT"],
            allow_headers=["Content-Type", "Authorization"],
        )))
    """

    __slots__ = ("config",)

    def __init__(self, config: CORSConfig | None = None) -> None:
        self.config = config or CORSConfig()

    def _is_allowed_origin(self, origin: str) -> bool:
        """Check if the origin is in the allow list."""
        if "*" in self.config.allow_origins:
            return True
        return origin in self.config.allow_origins

    def _add_cors_headers(self, response: AnyResponse, origin: str) -> AnyResponse:
        """Add CORS headers to a response."""
        cfg = self.config

        # Origin header
        if "*" in cfg.allow_origins and not cfg.allow_credentials:
            response = response.with_header("Access-Control-Allow-Origin", "*")
        else:
            response = response.with_header("Access-Control-Allow-Origin", origin)
            response = response.with_header("Vary", "Origin")

        # Credentials
        if cfg.allow_credentials:
            response = response.with_header("Access-Control-Allow-Credentials", "true")

        # Expose headers
        if cfg.expose_headers:
            response = response.with_header(
                "Access-Control-Expose-Headers",
                ", ".join(cfg.expose_headers),
            )

        return response

    def _preflight_response(self, origin: str, request_method: str | None) -> AnyResponse:
        """Build a preflight response with all CORS headers."""
        cfg = self.config
        response = Response(body="", status=204)
        response = self._add_cors_headers(response, origin)

        # Preflight-specific headers
        if request_method:
            response = response.with_header(
                "Access-Control-Allow-Methods",
                ", ".join(cfg.allow_methods),
            )

        if cfg.allow_headers:
            response = response.with_header(
                "Access-Control-Allow-Headers",
                ", ".join(cfg.allow_headers),
            )

        response = response.with_header("Access-Control-Max-Age", str(cfg.max_age))

        return response

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        """Process the request with CORS handling."""
        origin = request.headers.get("origin")

        # No Origin header — not a CORS request
        if origin is None:
            return await next(request)

        # Check if origin is allowed
        if not self._is_allowed_origin(origin):
            return await next(request)

        # Preflight request
        if request.method == "OPTIONS":
            request_method = request.headers.get("access-control-request-method")
            return self._preflight_response(origin, request_method)

        # Actual request — add CORS headers to the response
        response = await next(request)
        return self._add_cors_headers(response, origin)
