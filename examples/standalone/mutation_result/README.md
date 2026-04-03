# MutationResult

Demonstrates `MutationResult` progressive enhancement for POST, DELETE, and PATCH mutations. Each handler serves three UX flows from a single return value:

- **htmx + fragments**: renders OOB fragments (fast, no page reload)
- **htmx + no fragments**: sends HX-Redirect
- **non-htmx**: 303 server redirect (plain forms work too)

## Run

```bash
python app.py
```

## Test

```bash
pytest test_app.py
```
