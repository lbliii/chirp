# Forum Production Checklist

Forum-shaped apps stress a different part of Chirp than marketing pages: route
dispatch is rarely the first bottleneck. The hot path is usually database
access, permission checks, template rendering, session storage, and live
notification fanout.

## Database Shape

Keep forum reads index-friendly. A typical play-by-post forum should have
indexes along these paths:

- Boards to threads: `(board_id, last_post_at DESC)` or `(board_id, bumped_at DESC)`.
- Thread pages: `(thread_id, created_at)` or `(thread_id, id)`.
- Slugs: unique `(board_id, slug)` for threads and unique board slugs.
- Unread state: `(user_id, thread_id)` plus any notification feed ordering.
- Notifications: `(user_id, created_at DESC)` and a partial or composite index
  for unread notifications if the database supports it.

Avoid offset pagination on long threads once data grows. Prefer keyset pagination
by post id or creation timestamp.

## Shared Runtime State

One web replica is the simplest production launch shape. Before adding Railway
replicas, move these out of process-local memory:

- Sessions: use `RedisSessionStore` or another shared store.
- Rate limits: use Redis-backed counters.
- Notification/unread counters: store in Postgres or Redis.
- SSE fanout: publish events through Redis or another shared bus.
- Caches: use Redis and keys that include query string, auth/public shape, and
  htmx response shape.

Railway does not provide sticky sessions for replicas, so a user can hit
different app instances across requests.

## Caching

Cache only public or explicitly scoped forum pages. Do not globally cache
logged-in pages unless the cache key includes every input that changes the
rendered HTML.

Chirp's default cache key includes the path, query string, and htmx shape, so
`/threads?page=1`, `/threads?page=2`, full-page responses, and htmx fragments do
not collide. `CacheMiddleware` also bypasses requests carrying `Cookie` or
`Authorization` headers. It still does not know about locale, tenant, custom
feature flags, or other app-specific variants. Include those in a custom key for
scoped pages, or leave those pages uncached.

`CacheMiddleware` does not cache QUERY responses. Chirp's provisional QUERY
key design covers exact body bytes and request metadata, but cache reads and
writes remain disabled until the explicit opt-in, validator, streaming, and
backend-failure contracts are complete. Do not treat the presence of a key
builder as permission to cache body-bearing requests globally. Experimental
opt-in is available only by manually passing `query_key_func=query_cache_key`
to `CacheMiddleware`; configuration-managed caching remains GET-only. Use a
shared backend, short TTLs, explicit invalidation, and application-specific vary
headers before considering it for public, repeatable searches.

## SSE

SSE is good for forum notifications, unread counters, active thread tails, and
presence-style hints. Keep each stream scoped narrowly:

- User notification stream: one per logged-in user.
- Thread tail stream: one per active thread view.
- Avoid a single global forum stream that every browser receives.

With one web replica, in-process event dispatch is acceptable for early launch.
With multiple replicas, use shared fanout; otherwise a browser connected to
replica A will miss an event produced on replica B.

For shell placement, OOB targets, replayable event ids, and reconnect testing,
see [Realtime Product Patterns](../realtime-production.md).

## Rendering

Prefer returning the narrowest correct Chirp return type:

- `Page` for full page and boosted navigation negotiation.
- `Fragment` or `MutationResult` for local form/list updates.
- `OOB` for counters and shell regions that update alongside a primary swap.
- `EventStream` only for post-load live updates, not initial page rendering.

If page navigation uses a persistent app shell, declare the layout outlet with
`{# outlet: main #}` or rely on `use_chirp_ui(app)` with
`chirpui/app_shell_layout.html`. The response must include the selector targeted
by inherited `hx-select`, usually `#page-content`.

## Railway Notes

Use the Railway guide for platform setup: [Railway Deployment](railway.md).
For a forum, the important deployment order is:

1. Postgres first.
2. Single web replica.
3. Healthcheck and pre-deploy migrations.
4. Redis-backed sessions and shared events.
5. Additional replicas after the shared-state path is proven.
