"""Passkey config derives rp_id/origin from the incoming request host."""

from __future__ import annotations

import passkey_config

from chirp.http.headers import Headers
from chirp.http.request import Request, _LazyCookies, _LazyQueryParams


def _request(host: str, *, current_url: str | None = None, extra: dict[str, str] | None = None) -> Request:
    headers = {"host": host}
    if current_url is not None:
        headers["hx-current-url"] = current_url
    if extra:
        headers.update(extra)
    return Request(
        method="GET",
        path="/settings/security",
        headers=Headers(tuple((k.encode(), v.encode()) for k, v in headers.items())),
        query=_LazyQueryParams(b""),
        path_params={},
        http_version="1.1",
        server=(host.split(":")[0], int(host.split(":")[1]) if ":" in host else 80),
        client=("127.0.0.1", 12345),
        cookies=_LazyCookies(""),
        request_id="test-id",
        _receive=lambda: {"body": b"", "more_body": False},
    )


def test_config_for_request_uses_localhost_host(monkeypatch):
    monkeypatch.delenv("CHIRP_PASSKEY_ORIGIN", raising=False)
    cfg = passkey_config.config_for_request(_request("127.0.0.1:8000"))
    assert cfg.origin == "http://127.0.0.1:8000"
    assert cfg.rp_id == "127.0.0.1"


def test_config_for_request_prefers_hx_current_url(monkeypatch):
    monkeypatch.delenv("CHIRP_PASSKEY_ORIGIN", raising=False)
    cfg = passkey_config.config_for_request(
        _request("localhost:8000", current_url="http://127.0.0.1:8000/settings/security")
    )
    assert cfg.origin == "http://127.0.0.1:8000"
    assert cfg.rp_id == "127.0.0.1"


def test_config_for_request_env_override(monkeypatch):
    monkeypatch.setenv("CHIRP_PASSKEY_ORIGIN", "https://lucky.example.com")
    monkeypatch.setenv("CHIRP_PASSKEY_RP_ID", "lucky.example.com")
    cfg = passkey_config.config_for_request(_request("127.0.0.1:8000"))
    assert cfg.origin == "https://lucky.example.com"
    assert cfg.rp_id == "lucky.example.com"


def test_config_for_request_strips_trailing_slash_from_env_origin(monkeypatch):
    monkeypatch.setenv("CHIRP_PASSKEY_ORIGIN", "https://lucky.example.com/")
    cfg = passkey_config.config_for_request(_request("127.0.0.1:8000"))
    assert cfg.origin == "https://lucky.example.com"


def test_config_for_request_uses_railway_public_domain(monkeypatch):
    monkeypatch.delenv("CHIRP_PASSKEY_ORIGIN", raising=False)
    monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "luckycat-production.up.railway.app")
    cfg = passkey_config.config_for_request(_request("luckycat-production.up.railway.app"))
    assert cfg.origin == "https://luckycat-production.up.railway.app"
    assert cfg.rp_id == "luckycat-production.up.railway.app"


def test_config_for_request_defaults_https_in_production(monkeypatch):
    monkeypatch.delenv("CHIRP_PASSKEY_ORIGIN", raising=False)
    monkeypatch.delenv("RAILWAY_PUBLIC_DOMAIN", raising=False)
    monkeypatch.setenv("CHIRP_ENV", "production")
    cfg = passkey_config.config_for_request(_request("app.example.com"))
    assert cfg.origin == "https://app.example.com"
    assert cfg.rp_id == "app.example.com"


def test_config_for_request_honors_x_forwarded_proto(monkeypatch):
    monkeypatch.delenv("CHIRP_PASSKEY_ORIGIN", raising=False)
    monkeypatch.delenv("RAILWAY_PUBLIC_DOMAIN", raising=False)
    cfg = passkey_config.config_for_request(
        _request("app.example.com", extra={"x-forwarded-proto": "https"})
    )
    assert cfg.origin == "https://app.example.com"
