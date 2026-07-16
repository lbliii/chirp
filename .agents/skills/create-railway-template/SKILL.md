---
name: create-railway-template
description: Create, publish, update, and verify polished zero-input Railway templates for Chirp applications. Use for Chirp Railway catalog issues, template or repository naming, application identity and visual design, favicons and marketplace assets, generated variable defaults, PostgreSQL service wiring, template metadata, disposable proof deployments, publication, or template smoke testing.
---

# Create Railway Template

Create templates that deploy without asking the user for configuration and prove the deployed application, not merely the template record.

Use the `use-railway` skill for Railway operations. Follow the repository's `AGENTS.md` maps before editing source or catalog collateral.

## Workflow

1. Select an eligible backlog issue with `scripts/backlog.py next` and inspect it with `scripts/backlog.py explain N`. Never take `[GF]` or `good first issue` work.
2. Define the product identity, follow [references/naming.md](references/naming.md), and apply [references/visual-quality.md](references/visual-quality.md). Build and verify the application in its own repository. Pin a release tag before using it as template source.
3. Turn the issue acceptance criteria into an evidence plan before cloud writes. Read [references/proof.md](references/proof.md).
4. Assign separate source, clean-proof, and public-demo roles. Create a dedicated empty proof project; do not use an existing demo as clean-deploy evidence.
5. In a separate temporary directory, link Railway explicitly to the proof project and confirm it is empty with `railway status --json` and `railway service list --json`.
6. Create the template from the intended source project and environment. Configure defaults for every variable before publication.
7. Publish with complete marketplace metadata, audit the serialized public template, then deploy its public code into the linked proof project without variable overrides.
8. Wait for terminal deployment states and prove representative product transitions, authorization and privacy boundaries, PostgreSQL identity, and persistence across required lifecycle operations.
9. Attach a verified public demo and update repository and catalog collateral only after clean proof passes. Read [references/catalog.md](references/catalog.md). Remove resources only with explicit user confirmation.

## Configure zero-input variables

- Give every non-optional template variable a non-empty default.
- Generate credentials with Railway expressions such as `${{ secret(32, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ") }}`. Never put resolved secrets in source, logs, or template metadata.
- Derive the complete generated-credential list from the application or catalog manifest. Do not special-case familiar token names.
- Set inter-service variables with case-sensitive references, for example `${{Postgres.DATABASE_URL}}` on the web service.
- For PostgreSQL, read [references/postgres.md](references/postgres.md) and mirror Railway's current official template rather than reconstructing values from a live deployment.
- Preserve the PostgreSQL volume mount and required mount path at `/var/lib/postgresql/data`.

## Establish product quality

- Use stable, predictable names for the repository, Railway template, project, services, variables, and release tags. Read [references/naming.md](references/naming.md).
- Give each template a product-specific visual premise while retaining a restrained Chirp family resemblance. Read [references/visual-quality.md](references/visual-quality.md).
- Ship a real favicon from the first release. Link it from every full-page shell and serve it with the correct image content type.
- Keep the primary task or data visible in the first viewport on authenticated utility screens. Do not reuse a marketing hero where it delays the working interface.
- Produce a marketplace card image that matches the shipped UI rather than a generic framework graphic.

## Publish metadata

Use a dedicated marketplace overview rather than the developer README. It must contain headings beginning with:

- `# Deploy and Host`
- `## About Hosting`
- `## Why Deploy`
- `## Common Use Cases`
- `## Dependencies for`
- `### Deployment Dependencies`

Publish with category, description, overview, image, and demo project in one command. Read back the returned ID, code, status, and URL.

## Audit before deployment

Immediately after publication, run:

```bash
python .agents/skills/create-railway-template/scripts/audit_public_template.py TEMPLATE_CODE \
  --require-generated web.CHIRP_SECRET_KEY
```

Repeat `--require-generated SERVICE.VARIABLE` for every manifest-declared credential, using the exact serialized service and variable names. The audit compares PostgreSQL against Railway's current official template, checks volume paths, rejects missing defaults, checks the web database reference, and verifies exact generated-secret expressions. If it fails, unpublish immediately and correct the draft.

## Prove a clean deployment

- Read [references/proof.md](references/proof.md) and execute the issue-specific evidence plan; generic health checks are necessary but insufficient.
- Reconfirm the current directory is linked to the disposable proof project immediately before `railway deploy --template CODE`.
- Treat any environment-variable prompt as a failed zero-input test. Do not answer it and continue.
- Be aware that `railway deploy --template` deploys directly into the linked project and may require a TTY. Never run it from a directory linked to the live demo.
- Poll every created service until each reaches `SUCCESS`; a queued build or created template is not proof.
- Exercise `/health`, `/ready`, static assets, authentication, and representative product state transitions through the public application surface.
- Assert that every full-page response contains a favicon link and that the target returns `200` with an image content type. Visually inspect it at browser-tab size.
- Verify the application uses the newly created PostgreSQL service, not another database in the project.
- List deployed volumes and require exactly one PostgreSQL volume attached at `/var/lib/postgresql/data`, with no unattached volumes left in the proof environment.
- Inspect the deployed web service's raw environment configuration, not resolved variable-list output, without printing values and require `DATABASE_URL` to remain the exact `${{Postgres.DATABASE_URL}}` reference rather than a copied URL.
- Record project, environment, service, deployment, and smoke-test IDs without printing credential values.

## Finalize collateral

- Change template status from draft to published and record the public deployment URL.
- Record the latest successful clean smoke timestamp.
- Follow [references/catalog.md](references/catalog.md) to update the current catalog source of truth, README deployment guidance, and marketplace overview.
- Keep the repository, template code, marketplace title, services, domains, favicon identity, and screenshot names aligned with the naming standard.
- Run the repository's required tests and formatting checks.
- Commit and push source collateral only after public state and repository metadata agree.

## Safety

- Never publish first and defer default configuration.
- Never test in the live demo project.
- Never expose resolved secrets when inspecting variables; print only names, booleans, hosts, or lengths.
- Never delete services, volumes, environments, or proof projects without explicit user confirmation.
- If publication succeeds but validation fails, unpublish before continuing.
