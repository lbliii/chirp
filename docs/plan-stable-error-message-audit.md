# Plan: Stable API Error-Message Audit

**Status**: Completed initial audit
**Created**: 2026-05-03
**Completed**: 2026-05-03
**Steward**: Public Surface Steward + Routing/HTTP/Middleware Stewards

---

## Result

The initial stable API error-message audit is complete. The pass focused on
messages that app authors see while wiring routes, form parsing, and sessions.

Most high-risk surfaces were already actionable:

- `BlockNotFoundError` names the template, block, optional OOB escape hatch, and
  likely fix.
- `Page(...)` misuse points users toward `Template(...)`.
- `url_for()` errors list known names or the missing path parameters.
- Suspense missing-block errors include nearby-block suggestions.
- CSRF/auth middleware ordering errors name the middleware that must be added.

## Patched Messages

| Surface | Change |
|---------|--------|
| Router 405 | `MethodNotAllowed` raised from routing now includes the attempted method, request path, and allowed methods in the detail string while preserving the `Allow` header. |
| Form parsing | Unsupported content-type errors now name the supported encodings and point JSON/custom payload users at `request.body`. |
| Multipart parsing | Missing boundary errors now name the required `multipart/form-data; boundary=...` shape and note browsers set it automatically for normal file-upload forms. |
| Sessions | Empty `SessionConfig.secret_key` errors now point at `SessionConfig(secret_key=app.config.secret_key)`, `AppConfig(secret_key=...)`, and `CHIRP_SECRET_KEY`. |

## Follow-Ups

1. Audit stable auth decorator HTTPError details for whether route authors need
   configurable redirect/401 guidance in error bodies.
2. Audit `FormBindingError` field messages against more complex dataclass
   annotations once validation docs settle.
3. Audit stable `App` lifecycle errors in a separate pass if 1.0 work changes
   freeze timing or `mount_app` behavior.

## Validation

- `uv run pytest tests/test_router.py tests/test_forms.py tests/test_sessions.py -q`
- `uv run ruff check src/chirp/routing/router.py src/chirp/http/forms.py src/chirp/middleware/sessions.py tests/test_router.py tests/test_forms.py tests/test_sessions.py`
