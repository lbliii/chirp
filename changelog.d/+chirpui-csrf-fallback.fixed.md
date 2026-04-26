**ChirpUI CSRF fallback** — `use_chirp_ui()` now avoids noisy empty-token warnings in apps without `CSRFMiddleware`, while real CSRF middleware still owns the template global when installed.
