**Middleware security defaults** — auth rate limiting now uses the socket client address by default instead of trusting `X-Forwarded-For`, credentialed wildcard CORS is rejected, and `app.check()` flags wildcard `allowed_hosts` outside development.

  **Migration** — Apps behind a trusted proxy that intentionally key auth rate limits by `X-Forwarded-For` must pass `AuthRateLimitConfig(key_header="x-forwarded-for")`; credentialed CORS must list explicit origins.
