# Forum Shell

A compact ChirpUI forum pattern inspired by richer play-by-post apps.

It demonstrates:

- mounted page-directory routing
- `Page.mounted(...)`
- app-shell layout contracts
- `FormContract` on mounted POST routes
- `form_from()` with repeated `list[int]` fields
- a narrow `JSONResponse` data island for mention search
- one OOB update for shell-level unread count
- hypermedia test helpers for full-page, fragment, OOB, and id assertions

Run:

```bash
python app.py
```
