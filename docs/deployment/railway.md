# Railway Deployment

This guide is the recommended production shape for Chirp apps on Railway,
especially logged-in forum-style apps with htmx navigation, sessions, database
writes, and SSE updates.

For database indexes, cache scope, and SSE fanout in forum-shaped apps, see
[Forum Production Checklist](forum-production.md).

## App Config

Use `AppConfig.from_env()` so Railway deployment variables are handled in one
place:

```python
from chirp import App, AppConfig

config = AppConfig.from_env()
app = App(config=config)
```

On Railway, `from_env()` falls back to the platform `PORT`, binds to
`0.0.0.0` when a Railway environment is detected, and includes
`RAILWAY_PUBLIC_DOMAIN` plus `healthcheck.railway.app` in `allowed_hosts` when
`CHIRP_ALLOWED_HOSTS` is not set.

Set these variables on the web service:

```text
CHIRP_ENV=production
CHIRP_DEBUG=0
CHIRP_SECRET_KEY=<generated secret>
CHIRP_LOG_FORMAT=json
CHIRP_LOG_LEVEL=info
```

`CHIRP_LOG_FORMAT=json` also installs Chirp's own JSON log formatter (matching
the server envelope), and `CHIRP_LOG_LEVEL` sets the log threshold
(`debug`/`info`/`warning`/`error`/`critical`, default `info`).

If the app has a custom domain, set allowed hosts explicitly:

```text
CHIRP_ALLOWED_HOSTS=forum.example.com,healthcheck.railway.app
```

## Start Command

Use the app's normal entrypoint and let Chirp launch Pounce in production mode:

```bash
uv run python app.py
```

The app entrypoint should call `app.run()` only under `if __name__ == "__main__"`.

## Healthcheck

Add a cheap unauthenticated endpoint:

```python
@app.route("/health")
def health():
    return "ok"
```

Configure Railway's healthcheck path to `/health`. Railway only promotes the new
deployment after this endpoint returns `200`; it does not use the healthcheck
for continuous monitoring.

## Database Migrations

Run schema migrations as a Railway pre-deploy command. Pre-deploy commands run
after build and before the new deployment goes live, have access to service
environment variables and private networking, and should fail non-zero when the
migration fails.

Use the `chirp migrate` one-shot command as the pre-deploy command, and set
`CHIRP_SKIP_MIGRATIONS=1` on the web service so replicas do not also run
migrations on boot (which would race when you scale past one replica):

```bash
# Pre-deploy command (one-shot, fails the deploy on a migration error)
chirp migrate --db "$DATABASE_URL" --migrations-dir migrations
```

```text
# Web service variable — the pre-deploy job owns migration application
CHIRP_SKIP_MIGRATIONS=1
```

`chirp migrate` does not boot the app (no freeze, no contract checks) — it just
connects, applies pending migrations, and exits `1` on failure (including a
checksum-drift edit of an already-applied migration). When the app boots with
`CHIRP_SKIP_MIGRATIONS=1` it logs a `lifecycle:migrations-skipped` warning so a
missing pre-deploy job (and the resulting stale schema) is visible in logs.

Do not put volume-dependent work in the pre-deploy command. Railway runs
pre-deploy commands in a separate container and volumes are not mounted there.

## Storage

Use managed Postgres for application data. Use Redis for shared runtime state
once the app needs more than one web replica. Use object storage for uploads,
avatars, and attachments.

Avoid Railway volumes for core forum data. Services with attached volumes can
have deployment downtime even when a healthcheck is configured.

## Scaling

Start with one web replica. Add more only after sessions, rate limits, caches,
and SSE fanout are backed by shared services such as Redis.

Railway can horizontally scale with replicas, but public traffic is randomly
distributed and sticky sessions are not available. Any state kept only in one
process can be invisible to requests that land on another replica.

## References

- [Railway public networking](https://docs.railway.com/public-networking)
- [Railway healthchecks](https://docs.railway.com/reference/healthchecks)
- [Railway pre-deploy commands](https://docs.railway.com/guides/pre-deploy-command)
- [Railway scaling](https://docs.railway.com/reference/scaling)
- [Railway volumes](https://docs.railway.com/volumes)
