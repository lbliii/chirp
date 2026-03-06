# Auth

A minimal session-auth example with a login form, protected dashboard, and
logout flow. It demonstrates `SessionMiddleware`, `AuthMiddleware`,
`@login_required`, password hashing helpers, and safe redirect handling.

## Run

```bash
cd examples/auth && python app.py
```

## Test

```bash
pytest examples/auth/
```
