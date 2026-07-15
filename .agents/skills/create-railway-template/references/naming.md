# Chirp Railway template naming

Use names that stay legible across GitHub, Railway, the marketplace, logs, environment references, and the catalog.

## Product and repository

| Surface | Convention | Example |
| --- | --- | --- |
| Product | `Chirp <Product>` in title case | `Chirp Hookbox` |
| Repository | `chirp-<product>` in lowercase kebab-case | `chirp-hookbox` |
| Template code | same stable repository slug | `chirp-hookbox` |
| Railway project | same product display name | `Chirp Hookbox` |
| Python package | repository slug unless it is importable code | `chirp-hookbox` |
| Release tag | semantic version with `v` prefix | `v0.1.3` |

Do not accept a generated template suffix such as `-1` as the canonical public code. Unpublish stale collisions or choose the stable code intentionally before publishing links.

## Services and environments

- Name the application service `web` when there is one public HTTP service.
- Name the primary database `Postgres` so `${{Postgres.DATABASE_URL}}` stays consistent and case-sensitive.
- Use descriptive lowercase kebab-case names for additional services, such as `worker` or `email-dispatch`.
- Use `production` for the public template environment and explicit names such as `template-proof` for disposable validation projects.
- Never allow generated proof suffixes such as `web-jfkh` or `Postgres-gHLN` into published metadata.

## Variables

- Use uppercase snake case.
- Prefix product-specific variables with the product noun, for example `HOOKBOX_ADMIN_TOKEN`.
- Keep shared Chirp variables under `CHIRP_`.
- Use ecosystem-standard names for dependencies, especially `DATABASE_URL`, `PORT`, and PostgreSQL's official variables.
- Name credentials by purpose, not implementation: prefer `HOOKBOX_INGRESS_TOKEN` over `WEBHOOK_SECRET_1`.

## Assets and receipts

- Use stable source names: `favicon.svg`, `railway-marketplace.png`, and `railway-template-readme.md`.
- Name smoke captures and proof projects with the template slug and purpose, without customer or private project names.
- Keep the manifest `slug`, public template code, repository slug, and deploy URL path identical.
