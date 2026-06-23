"""Passkey relying-party config — env-aware for Railway deploy."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from chirp.http.request import Request
from chirp.security.passkeys import PasskeyConfig

# WebAuthn requires rp_id to be a registrable suffix of origin. Override on Railway:
#   CHIRP_PASSKEY_RP_ID=your-app.up.railway.app
#   CHIRP_PASSKEY_ORIGIN=https://your-app.up.railway.app
_ORIGIN = os.environ.get("CHIRP_PASSKEY_ORIGIN", "http://localhost:8000")
_RP_ID = os.environ.get("CHIRP_PASSKEY_RP_ID", "localhost")

PASSKEY_CONFIG = PasskeyConfig(
    rp_id=_RP_ID,
    rp_name="Lucky Cat",
    origin=_ORIGIN,
)


def _origin_from_request(request: Request) -> str:
    """Derive the browser origin from the incoming request."""
    current = request.headers.get("hx-current-url")
    if current:
        parsed = urlparse(current)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"

    host = request.headers.get("host", "localhost:8000")
    proto = request.headers.get("x-forwarded-proto", "http").split(",", 1)[0].strip()
    if proto not in ("http", "https"):
        proto = "http"
    return f"{proto}://{host}"


def config_for_request(request: Request) -> PasskeyConfig:
    """Return passkey RP config for this request.

    When ``CHIRP_PASSKEY_ORIGIN`` is set, that origin (and optional
    ``CHIRP_PASSKEY_RP_ID``) wins — for production deploys behind a stable public
    URL. Otherwise derive from the request so ``localhost`` vs ``127.0.0.1`` and
    dev ports match what the browser actually uses (a common local footgun).
    """
    env_origin = os.environ.get("CHIRP_PASSKEY_ORIGIN")
    if env_origin:
        rp_id = (
            os.environ.get("CHIRP_PASSKEY_RP_ID") or urlparse(env_origin).hostname or "localhost"
        )
        return PasskeyConfig(rp_id=rp_id, rp_name="Lucky Cat", origin=env_origin)

    origin = _origin_from_request(request)
    hostname = urlparse(origin).hostname or "localhost"
    return PasskeyConfig(rp_id=hostname, rp_name="Lucky Cat", origin=origin)
