---
title: HTTP QUERY Interoperability
description: Browser, Pounce, ASGI, proxy, retry, redirect, body-limit, and observability evidence for experimental HTTP QUERY routes.
draft: false
weight: 45
lang: en
type: doc
tags: [deployment, http-query, pounce, cors, proxy]
keywords: [QUERY, RFC 10008, Pounce, HTTP/2, HTTP/3, CORS, Nginx, retry]
category: guide
---

Chirp's HTTP `QUERY` support remains experimental and explicit-route only. The
interoperability suite proves that the exact method and body reach the same
Chirp handler through Pounce HTTP/1.1, HTTP/2, and HTTP/3, Uvicorn, and a local
Nginx reverse proxy. Real Chromium tests cover same-origin Fetch and a
cross-origin CORS preflight.

Start with [[docs/build-apps/pages-navigation/http-query|Experimental HTTP
QUERY]] for GET-vs-QUERY guidance, route setup, response semantics, cache
opt-in, and the current release-gate decision.

The evidence does **not** mean every CDN or proxy accepts QUERY. Verify your
exact production path and keep a direct-origin or ordinary GET fallback.

## Required operator choices

- Add `QUERY` to `CORSConfig.allow_methods` and allow the declared
  `Content-Type` header for cross-origin browser calls.
- Confirm proxies preserve the method and body. A visible unsupported-method
  response is safer than rewriting the request to POST.
- Keep raw query bodies out of access logs, traces, and error reporting unless
  an explicit redaction policy exists. Pounce's tested access-log, metric, and
  span inputs identify QUERY without carrying its body bytes.
- Align Pounce's request-size ceiling with `AppConfig.max_request_body_size`.
- Treat retries and HTTP/3 0-RTT as possible replays. QUERY handlers must remain
  safe and idempotent.

`307` repeats QUERY and its body; `303` follows the equivalent resource with
GET. Use an application-owned GET equivalent when a result needs a durable,
bookmarkable identity.

For the complete matrix, commands, versions, caveats, and executable test map,
see the
[checked-in interoperability report](https://github.com/lbliii/chirp/blob/main/docs/http-query-interoperability.md).
