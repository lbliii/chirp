# Forum Shell

A compact ChirpUI forum pattern inspired by richer play-by-post apps.

It demonstrates:

- mounted page-directory routing
- `Page.mounted(...)`
- named route reversal with `url_for(...)`
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

Interesting paths:

- `/boards` renders the mounted page shell.
- `/boards/ic` swaps the board list/detail area under the shell.
- `/boards/ic/threads/market-rain` posts replies, binds repeated mention ids, and updates the
  unread count with an OOB fragment.
- `/mentionables/search?q=jun` returns the JSON data island used by mention search.
