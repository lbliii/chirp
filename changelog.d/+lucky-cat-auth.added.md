🔐 **Lucky Cat — authentication showcase.** The flagship ChirpUI example now
demonstrates Chirp's auth subsystem end to end, exercising all three gating
levels rather than a blanket lockdown:

  **Full-page gating** — `@login_required` on the account section (`/portfolio`,
  `/activity`, `/trade`, `/settings`, `/watchlist`); an anonymous hit redirects to
  `/login?next=…`. **Component gating** — `current_user()` conditional chrome: the
  topbar swaps between a "Sign in" link and the user menu + Sign-out (and reveals
  the $MEOW balance, the notifications bell, and the Deposit action), and the
  watchlist star on the *public* markets grid becomes a "sign in to star" link.
  **Action gating** — `@login_required` on the mutation routes (deposit, place /
  cancel order, convert, star toggle, notifications-read) as the security backstop.

  The sign-in flow is return-type-driven: `ValidationError` re-renders the login
  form in place (422) on bad credentials, and a clean sign-in returns `FormAction`
  (HX-Redirect for htmx → a full reload) so the persistent topbar repaints its
  auth state. Public market data (the
  markets grid and a market's detail page) stays browsable without an account.
  Built on `AuthMiddleware` + `login()`/`logout()` + a single in-memory demo
  account (`users.py`), with passwords hashed via `chirp.security.passwords`
  (stdlib scrypt fallback — no extra dependency).
