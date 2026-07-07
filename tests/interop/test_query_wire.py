"""Real-wire HTTP QUERY interoperability proof for issue #532."""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import logging
import shutil
import socket
import ssl
import subprocess
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from pounce.testing import TestServer

from tests.interop.query_app import QUERY_MEDIA_TYPE, make_probe_app

pytestmark = [pytest.mark.issue(532), pytest.mark.integration]

_BODY = b"facet=birds&region=north&private_token=do-not-log"
_HEADERS = {"Content-Type": QUERY_MEDIA_TYPE}


def _assert_fingerprint(text: str, body: bytes, *, version: str) -> None:
    assert 'data-method="QUERY"' in text
    assert f'data-http-version="{version}"' in text
    assert f'data-length="{len(body)}"' in text
    assert f'data-sha256="{hashlib.sha256(body).hexdigest()}"' in text
    assert body.decode() not in text


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_tcp(port: int, *, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise AssertionError(f"server on port {port} did not become ready within {timeout}s")


def _test_certificate(tmp_path: Path) -> tuple[Path, Path]:
    cryptography = pytest.importorskip("cryptography")
    del cryptography
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1))
        .not_valid_after(dt.datetime.now(dt.UTC) + dt.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(__import__("ipaddress").ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return cert_path, key_path


@contextmanager
def _uvicorn_server(app: Any) -> Iterator[str]:
    uvicorn = pytest.importorskip("uvicorn")
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            lifespan="on",
            loop="asyncio",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        _wait_for_tcp(port)
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        assert not thread.is_alive(), "Uvicorn did not stop after the interoperability probe"


def test_pounce_http1_raw_wire_preserves_query_method_and_body() -> None:
    app, state = make_probe_app()
    with TestServer(app) as server, socket.create_connection((server.host, server.port)) as sock:
        sock.settimeout(2)
        request = (
            b"QUERY /query HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Type: application/x-www-form-urlencoded\r\n"
            + f"Content-Length: {len(_BODY)}\r\n".encode()
            + b"Connection: close\r\n\r\n"
            + _BODY
        )
        sock.sendall(request)
        response = bytearray()
        while True:
            try:
                chunk = sock.recv(65_536)
            except TimeoutError:
                break
            if not chunk:
                break
            response.extend(chunk)

    assert response.startswith(b"HTTP/1.1 200")
    _assert_fingerprint(response.decode(errors="replace"), _BODY, version="1.1")
    assert state.seen[0].body == _BODY
    assert state.mutations == 0


def test_pounce_http2_tls_preserves_query_method_and_body(tmp_path: Path) -> None:
    pytest.importorskip("h2")
    cert_path, key_path = _test_certificate(tmp_path)
    app, state = make_probe_app()
    with (
        TestServer(
            app,
            ssl_certfile=str(cert_path),
            ssl_keyfile=str(key_path),
        ) as server,
        httpx.Client(
            http2=True,
            verify=ssl.create_default_context(cafile=str(cert_path)),
            trust_env=False,
        ) as client,
    ):
        response = client.request(
            "QUERY",
            f"https://{server.host}:{server.port}/query",
            headers=_HEADERS,
            content=_BODY,
        )

    assert response.status_code == 200
    assert response.http_version == "HTTP/2"
    _assert_fingerprint(response.text, _BODY, version="2")
    assert state.seen[0].body == _BODY
    assert state.mutations == 0


def _http3_query(server: TestServer, body: bytes) -> tuple[dict[bytes, bytes], bytes]:
    pytest.importorskip("zoomies")
    from zoomies.core import QuicConfiguration, QuicConnection
    from zoomies.events import (
        H3DataReceived,
        H3HeadersReceived,
        HandshakeComplete,
        StreamDataReceived,
    )
    from zoomies.h3 import H3Connection

    server_addr = (server.host, server.port)
    client = QuicConnection(
        QuicConfiguration(is_client=True, verify_mode=False, server_name="localhost")
    )
    h3 = H3Connection(sender=client)
    client.connect()
    response_headers: dict[bytes, bytes] = {}
    response_body = bytearray()
    handshake_complete = False
    response_complete = False

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(0.2)
        deadline = time.monotonic() + 8
        request_sent = False
        while time.monotonic() < deadline and not response_complete:
            now = time.monotonic()
            for datagram in client.send_datagrams(now=now):
                sock.sendto(datagram, server_addr)
            try:
                datagram, _ = sock.recvfrom(65_535)
            except TimeoutError:
                continue
            events = client.datagram_received(datagram, server_addr, now=time.monotonic())
            if any(isinstance(event, HandshakeComplete) for event in events):
                handshake_complete = True
            if handshake_complete and not request_sent:
                h3.send_headers(
                    0,
                    [
                        (b":method", b"QUERY"),
                        (b":scheme", b"https"),
                        (b":authority", b"localhost"),
                        (b":path", b"/query"),
                        (b"content-type", QUERY_MEDIA_TYPE.encode()),
                        (b"content-length", str(len(body)).encode()),
                    ],
                    end_stream=False,
                )
                h3.send_data(0, body, end_stream=True)
                request_sent = True
            for event in events:
                if not isinstance(event, StreamDataReceived):
                    continue
                for h3_event in h3.handle_event(event):
                    if isinstance(h3_event, H3HeadersReceived):
                        response_headers.update(h3_event.headers)
                    elif isinstance(h3_event, H3DataReceived):
                        response_body.extend(h3_event.data)
                        response_complete = h3_event.end_stream

    assert handshake_complete, "HTTP/3 TLS handshake did not complete"
    assert response_complete, "HTTP/3 response did not complete"
    return response_headers, bytes(response_body)


def test_pounce_http3_preserves_query_method_and_body(tmp_path: Path) -> None:
    pytest.importorskip("zoomies")
    cert_path, key_path = _test_certificate(tmp_path)
    app, state = make_probe_app()
    with TestServer(
        app,
        ssl_certfile=str(cert_path),
        ssl_keyfile=str(key_path),
        http3_enabled=True,
        http3_zero_rtt_enabled=False,
    ) as server:
        headers, body = _http3_query(server, _BODY)

    assert headers[b":status"] == b"200"
    _assert_fingerprint(body.decode(), _BODY, version="3")
    assert state.seen[0].body == _BODY
    assert state.mutations == 0


def test_uvicorn_asgi_transport_preserves_query_method_and_body() -> None:
    app, state = make_probe_app()
    with _uvicorn_server(app) as base_url:
        response = httpx.request(
            "QUERY",
            f"{base_url}/query",
            headers=_HEADERS,
            content=_BODY,
            trust_env=False,
        )

    assert response.status_code == 200
    _assert_fingerprint(response.text, _BODY, version="1.1")
    assert state.seen[0].body == _BODY
    assert state.mutations == 0


def test_query_redirects_preserve_or_switch_method_per_status() -> None:
    app, state = make_probe_app()
    with TestServer(app) as server, httpx.Client(follow_redirects=True, trust_env=False) as client:
        retained = client.request(
            "QUERY",
            f"{server.url}/redirect/temporary",
            headers=_HEADERS,
            content=_BODY,
        )
        equivalent = client.request(
            "QUERY",
            f"{server.url}/redirect/equivalent",
            headers=_HEADERS,
            content=_BODY,
        )

    assert [item.status_code for item in retained.history] == [307]
    _assert_fingerprint(retained.text, _BODY, version="1.1")
    assert [item.status_code for item in equivalent.history] == [303]
    assert 'data-method="GET"' in equivalent.text
    assert [request.method for request in state.seen] == ["QUERY"]
    assert state.mutations == 0


def test_retry_after_connection_failure_executes_read_once() -> None:
    port = _free_port()
    app, state = make_probe_app()
    with pytest.raises(httpx.ConnectError):
        httpx.request(
            "QUERY",
            f"http://127.0.0.1:{port}/query",
            headers=_HEADERS,
            content=_BODY,
            trust_env=False,
            timeout=0.25,
        )

    with TestServer(app, port=port) as server:
        response = httpx.request(
            "QUERY",
            f"{server.url}/query",
            headers=_HEADERS,
            content=_BODY,
            trust_env=False,
        )

    assert response.status_code == 200
    assert len(state.seen) == 1
    assert state.seen[0].body == _BODY
    assert state.mutations == 0


def test_pounce_body_limit_rejects_query_before_dispatch() -> None:
    app, state = make_probe_app(chirp_body_limit=1_024)
    with TestServer(app, max_request_size=8) as server:
        response = httpx.request(
            "QUERY",
            f"{server.url}/query",
            headers=_HEADERS,
            content=b"123456789",
            trust_env=False,
        )

    assert response.status_code == 413
    assert state.seen == []
    assert state.mutations == 0


def test_access_log_identifies_query_without_body(monkeypatch: pytest.MonkeyPatch) -> None:
    import pounce._request_pipeline as pipeline

    calls: list[tuple[str, str, int]] = []
    monkeypatch.setattr(
        pipeline,
        "access_log",
        lambda method, target, status, *args, **kwargs: calls.append((method, target, status)),
    )
    app, state = make_probe_app()
    server = TestServer(app)
    server._server._config = replace(server._server._config, access_log=True)
    with server:
        response = httpx.request(
            "QUERY",
            f"{server.url}/query",
            headers=_HEADERS,
            content=_BODY,
            trust_env=False,
        )

    assert response.status_code == 200
    assert calls == [("QUERY", "/query", 200)]
    assert _BODY.decode() not in repr(calls)
    assert state.mutations == 0


def test_metrics_and_trace_span_identify_query_without_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pounce._otel as otel
    from pounce.metrics import PrometheusCollector
    from pounce.server import Server

    spans: list[dict[str, Any]] = []

    class _Span:
        def __enter__(self) -> _Span:
            return self

        def __exit__(self, *exc: object) -> None:
            del exc

    class _SpanManager:
        def __init__(self, *, service_name: str, enabled: bool) -> None:
            assert service_name == "pounce"
            assert enabled is True

        def create_request_span(self, **attributes: Any) -> _Span:
            spans.append(attributes)
            return _Span()

        @staticmethod
        def record_response(span: _Span, *, status_code: int, response_size: int) -> None:
            del span
            assert status_code == 200
            assert response_size > 0

        @staticmethod
        def record_exception(span: _Span, error: Exception) -> None:
            raise AssertionError(f"unexpected traced request failure: {error}") from error

    monkeypatch.setattr(otel, "RequestSpanManager", _SpanManager)
    monkeypatch.setattr(otel, "is_otel_available", lambda: False)

    app, state = make_probe_app()
    collector = PrometheusCollector()
    server = TestServer(app)
    config = replace(server._server._config, otel_endpoint="http://collector.invalid")
    server._server = Server(config, app, lifecycle_collector=collector)
    with server:
        response = httpx.request(
            "QUERY",
            f"{server.url}/query",
            headers=_HEADERS,
            content=_BODY,
            trust_env=False,
        )

    assert response.status_code == 200
    assert collector.snapshot()["requests_total"] == {("QUERY", "200"): 1}
    assert len(spans) == 1
    span = spans[0]
    assert span["method"] == "QUERY"
    assert span["path"] == "/query"
    assert span["scheme"] == "http"
    assert span["server_host"] == server.host
    assert span["server_port"] == server.port
    trace_headers = dict(span["headers"])
    assert trace_headers[b"content-type"] == QUERY_MEDIA_TYPE.encode()
    assert trace_headers[b"content-length"] == str(len(_BODY)).encode()
    assert "body" not in span
    assert _BODY.decode() not in repr(spans)
    assert state.mutations == 0


def test_nginx_reverse_proxy_preserves_query_method_and_body(tmp_path: Path) -> None:
    nginx = shutil.which("nginx")
    if nginx is None:
        pytest.skip("nginx is installed in the dedicated QUERY interoperability CI job")

    app, state = make_probe_app()
    proxy_port = _free_port()
    prefix = tmp_path / "nginx"
    prefix.mkdir()
    config = tmp_path / "nginx.conf"
    with TestServer(app) as backend:
        config.write_text(
            "\n".join(
                [
                    "events { worker_connections 32; }",
                    "http {",
                    "  access_log off;",
                    "  error_log stderr warn;",
                    "  server {",
                    f"    listen 127.0.0.1:{proxy_port};",
                    "    client_max_body_size 1m;",
                    "    location / {",
                    f"      proxy_pass http://127.0.0.1:{backend.port};",
                    "      proxy_http_version 1.1;",
                    "      proxy_set_header Host $host;",
                    "    }",
                    "  }",
                    "}",
                ]
            ),
            encoding="utf-8",
        )
        proc = subprocess.Popen(
            [nginx, "-c", str(config), "-p", str(prefix), "-g", "daemon off; master_process off;"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        try:
            _wait_for_tcp(proxy_port)
            response = httpx.request(
                "QUERY",
                f"http://127.0.0.1:{proxy_port}/query",
                headers=_HEADERS,
                content=_BODY,
                trust_env=False,
            )
        finally:
            proc.terminate()
            proc.wait(timeout=5)

    assert response.status_code == 200
    _assert_fingerprint(response.text, _BODY, version="1.1")
    assert state.seen[0].body == _BODY
    assert state.mutations == 0


async def test_zero_rtt_review_allows_query_replay_only_after_explicit_opt_in() -> None:
    """Exercise Pounce's pinned early-data method gate, not a copied method set."""
    pytest.importorskip("zoomies")
    from dataclasses import dataclass

    from pounce._h3_handler import _create_zoomies_datagram_protocol, _ZoomiesConnection
    from pounce.config import ServerConfig
    from zoomies.core import QuicConfiguration

    class _Quic:
        our_cids = (b"query-interop",)

        @staticmethod
        def send_datagrams() -> list[bytes]:
            return []

    class _H3:
        def __init__(self) -> None:
            self.statuses: list[bytes] = []

        def send_headers(
            self,
            *,
            stream_id: int,
            headers: list[tuple[bytes, bytes]],
            end_stream: bool = False,
        ) -> None:
            del stream_id, end_stream
            self.statuses.extend(value for name, value in headers if name == b":status")

        @staticmethod
        def send_data(*, stream_id: int, data: bytes, end_stream: bool = False) -> None:
            del stream_id, data, end_stream

    @dataclass(frozen=True, slots=True)
    class _Headers:
        stream_id: int
        method: bytes
        path: bytes
        is_0rtt: bool = True
        end_stream: bool = True

        @property
        def headers(self) -> tuple[tuple[bytes, bytes], ...]:
            return (
                (b":method", self.method),
                (b":scheme", b"https"),
                (b":authority", b"localhost"),
                (b":path", self.path),
                (b"content-type", QUERY_MEDIA_TYPE.encode()),
                (b"content-length", b"0"),
            )

    async def app(scope: Any, receive: Any, send: Any) -> None:
        del scope, receive, send

    default = ServerConfig()
    config = replace(
        default,
        ssl_certfile="cert.pem",
        ssl_keyfile="key.pem",
        http3_zero_rtt_enabled=True,
    )
    protocol_class = _create_zoomies_datagram_protocol(
        app,
        config,
        logging.getLogger("query-interop"),
        ("127.0.0.1", 4433),
        QuicConfiguration(certificate=b"cert", private_key=b"key"),
    )
    protocol = protocol_class()
    protocol.connection_made(MagicMock(spec=asyncio.DatagramTransport))
    h3 = _H3()
    connection = _ZoomiesConnection(
        quic=_Quic(),
        h3=h3,
        last_addr=("127.0.0.1", 5000),
    )

    protocol._handle_headers(
        connection,
        _Headers(stream_id=0, method=b"QUERY", path=b"/query"),
        connection.last_addr,
    )
    assert 0 in connection.stream_tasks
    query_task, _ = connection.stream_tasks[0]
    query_task.cancel()
    await asyncio.gather(query_task, return_exceptions=True)

    protocol._handle_headers(
        connection,
        _Headers(stream_id=4, method=b"POST", path=b"/mutation"),
        connection.last_addr,
    )
    assert 4 not in connection.stream_tasks
    assert h3.statuses == [b"425"]
    assert default.http3_zero_rtt_enabled is False
    assert config.http3_zero_rtt_enabled is True
