# Railway PostgreSQL template baseline

Railway's official `postgres` template is authoritative. Query it before configuring a Chirp template because image versions and defaults can change:

```graphql
query template($code: String!) {
  template(code: $code) { serializedConfig }
}
```

Send `{"code":"postgres"}` to `https://backboard.railway.com/graphql/v2`, or let `audit_public_template.py` query it.

As of the current Railway PostgreSQL 18 template, preserve these defaults:

| Variable | Default value |
| --- | --- |
| `PGDATA` | `/var/lib/postgresql/data/pgdata` |
| `PGHOST` | `${{RAILWAY_PRIVATE_DOMAIN}}` |
| `PGPORT` | `5432` |
| `PGUSER` | `${{ POSTGRES_USER }}` |
| `PGDATABASE` | `${{POSTGRES_DB}}` |
| `PGPASSWORD` | `${{POSTGRES_PASSWORD}}` |
| `POSTGRES_DB` | `railway` |
| `POSTGRES_USER` | `postgres` |
| `POSTGRES_PASSWORD` | `${{ secret(32, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ") }}` |
| `DATABASE_URL` | `postgresql://${{PGUSER}}:${{POSTGRES_PASSWORD}}@${{RAILWAY_PRIVATE_DOMAIN}}:5432/${{PGDATABASE}}` |
| `RAILWAY_DEPLOYMENT_DRAINING_SECONDS` | `60` |

The official template also defaults `SSL_CERT_DAYS` to `820` and defines `DATABASE_PUBLIC_URL` through the TCP proxy. A Chirp application needs only the private `DATABASE_URL`; retain the public URL only when the template includes a TCP proxy or Railway's data panel requires it.

Set both `deploy.requiredMountPath` and the volume mount to `/var/lib/postgresql/data` in the source template configuration. Railway may omit `deploy.requiredMountPath` from the serialized public template; the auditor accepts an omission, rejects a conflicting path, and always requires exactly one volume mount at the canonical path. On the application service, set `DATABASE_URL` to the exact case-sensitive service reference, normally `${{Postgres.DATABASE_URL}}`.
