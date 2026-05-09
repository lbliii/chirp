# Forum Shell

A compact ChirpUI shell fixture inspired by richer play-by-post apps.

This is not a full forum product. It is a regression fixture that keeps
product-shaped Chirp contracts executable: mounted pages, typed forms,
app-shell navigation, OOB shell state, and a narrow JSON data island.

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

What it intentionally does not demonstrate:

- product schemas or migrations
- account registration, permissions, moderation, or workflow state
- tenant/base-path URL policy
- production realtime replay or presence
- a general-purpose forum scaffold

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

Contract proof:

- `test_example_app_contract_coverage_is_strong` asserts mounted POST routes
  report `FormContract` coverage.
- boosted navigation tests assert shell outlet responses include `#page-content`
  and `#page-root`, not a full document.
- reply tests assert repeated fields bind through `form_from()` and OOB updates
  target the shell unread count.
