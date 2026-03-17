# Auth

A minimal session-auth example with a login form, protected dashboard, and
logout flow. It demonstrates `SessionMiddleware`, `AuthMiddleware`,
`@login_required`, password hashing helpers, and safe redirect handling.

## Run

```bash
PYTHONPATH=src python examples/standalone/auth/app.py
```

## Test

```bash
pytest examples/standalone/auth/
```
