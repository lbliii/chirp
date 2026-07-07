# HTTP QUERY Interoperability Report

**Status:** Experimental transport evidence for issue
[#532](https://github.com/lbliii/chirp/issues/532)

**Protocol contract:** [RFC 009](rfcs/009-http-query.md)

This report records what Chirp proves about carrying an RFC 10008 `QUERY`
request through browsers, ASGI servers, and a representative reverse proxy.
It does not promote QUERY to a stable or universally deployable feature.

## Automated matrix

| Path | Evidence | Expected result |
| --- | --- | --- |
| Pounce HTTP/1.1 | Raw TCP request in `tests/interop/test_query_wire.py` | Exact `QUERY` token and request bytes reach Chirp. |
| Pounce HTTP/2 | TLS/ALPN request with `httpx[http2]` | Chirp observes HTTP version `2` and the exact request bytes. |
| Pounce HTTP/3 | Real UDP/QUIC request with Pounce's `h3` extra and Zoomies | Chirp observes HTTP version `3` and the exact request bytes. |
| Alternate ASGI server | Uvicorn 0.32.0 live-server request | The same public Chirp app observes `QUERY` and the exact body. |
| Nginx reverse proxy | Local Nginx forwarding to Pounce | The method and body arrive unchanged; no POST rewrite occurs. |
| Browser Fetch | Real Chromium same-origin request | Fetch sends QUERY and receives the HTML response. |
| Browser CORS | Real Chromium cross-origin preflight and request | The request succeeds only when `CORSConfig.allow_methods` names `QUERY`. |
| Redirects | Live Pounce plus redirect-following client | `307` repeats QUERY and its body; `303` performs GET. |
| Retry | Failed connection followed by one explicit retry | The read handler executes once and no mutation route executes. |
| Body limits | Pounce limit smaller than Chirp's limit | Pounce returns `413` before the handler runs. |
| Access log | Pounce request-pipeline capture | Method, target, and status are present; raw request content is absent. |
| Metrics | Live Pounce `PrometheusCollector` | `http_requests_total` records `method="QUERY"` without the body. |
| Tracing | Live Pounce span-manager boundary | Span attributes receive method, path, protocol metadata, and headers—not body bytes. |

The dedicated `query-interop` CI job installs
`bengal-pounce[h2,h3]==0.8.2`, `httpx[http2]`, Uvicorn 0.32.0, and the Ubuntu
runner's Nginx package. The job prints the OS, Python, Pounce, HTTP client,
Uvicorn, Zoomies, and Nginx versions before running the matrix. The browser job
installs Chromium through Playwright and runs the CORS proof.

Run the non-browser matrix locally with:

```bash
uv sync --group dev
uv pip install "bengal-pounce[h2,h3]==0.8.2" "httpx[http2]>=0.27.0" "uvicorn==0.32.0"
uv run pytest tests/interop/test_query_wire.py -q
```

Nginx is optional locally; that test skips when the executable is absent. Run
the browser proof after installing Chromium:

```bash
uv sync --group dev --group browser
uv run playwright install chromium
uv run pytest tests/contracts/test_query_cors_browser.py -q
```

## 0-RTT and retry policy

Pounce disables HTTP/3 0-RTT by default. An operator must enable it explicitly.
QUERY is safe and idempotent under RFC 10008, so a replay is permitted at the
HTTP semantic layer, but application handlers must still be read-only. The
matrix asserts that its QUERY path never invokes the mutation route. It does
not claim that 0-RTT prevents replay or that a nonconforming application is
made safe by the server.

Automatic retries are similarly an operator/client decision. The test performs
one retry only after a connection failure where the first request never reached
the app. If an intermediary cannot determine whether a request was processed,
the application must tolerate replay or the client must use a GET equivalent
resource instead of retrying blindly.

## Deployment constraints and fallbacks

- CORS configuration must include both `QUERY` and the request's
  `Content-Type`; a browser blocks the request when the preflight response omits
  QUERY.
- Reverse proxies and CDNs need an explicit method/body preservation check.
  Unsupported intermediaries must return a visible error. Never rewrite QUERY
  to POST.
- Request bodies are not inherently private. The tested default access-log,
  metric, and span inputs omit body bytes; keep body capture off in additional
  error reporting and CDN diagnostics unless an explicit redaction policy
  exists.
- Pounce and Chirp enforce independent body ceilings. Use the lower effective
  limit intentionally and verify its `413` behavior.
- The portable fallback is a direct-origin QUERY request or a normal GET
  resource representing a bookmarkable subset/equivalent result.
- HTTP/3 proof requires Pounce's optional `h3` dependency and UDP reachability;
  lack of HTTP/3 does not change HTTP/1.1 or HTTP/2 semantics.

No CDN is certified by this report. CDN behavior changes independently and
must be verified against the exact service, plan, region, and configuration in
use.
