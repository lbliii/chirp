# Railway template proof

Prove the deployed product, not only the template record or container health.

## Plan evidence first

Translate every issue acceptance criterion into an evidence row before creating cloud resources. Record the product surface, action or transition, expected authorization and storage effects, proof method, and lifecycle state. Include explicit no-impact rows for acceptance criteria that do not apply.

At minimum, cover:

- a zero-input deployment from the public template code;
- health, readiness, static assets, and full-page shell behavior;
- representative create, update, completion, cancellation, retry, or recovery transitions for the product;
- administrator and private-user boundaries, including data that must not appear on public screens;
- PostgreSQL-backed state before and after restart;
- empty, error, desktop, and mobile states when the application exposes them.

Generic endpoint checks do not replace functional transitions. Exercise the database code paths most likely to differ between SQLite and PostgreSQL.

## Separate Railway roles

Treat these as distinct roles even when Railway eventually permits one project to serve more than one role:

1. The source project and environment are the reviewed inputs serialized into the template.
2. The clean-proof project starts empty and receives the public template without overrides.
3. The public-demo project is the retained marketplace demonstration after it passes the same functional checks.

Railway may reject the source project as its own demo. Never weaken clean-proof isolation merely to reuse a project. Confirm the chosen demo is attached to the published template through a public readback.

## Prove deployment and persistence

- Poll each created service to a terminal state. If a CLI restart or deployment command times out, inspect server-side deployment state before declaring failure or retrying.
- Query database identity through the deployed application or its actual connection and record the PostgreSQL version without credentials.
- Create durable state through the public application, restart the web service, and assert the same records and history remain.
- When required by the issue, prove rollback and roll-forward, shutdown and recovery, ejection to a user-approved repository, and an automatic deployment from a post-ejection commit.
- Treat ejection, repository creation, deletion, and other external writes as separately approval-gated operations.

## Browser and smoke-test discipline

- For pages with permanent SSE connections, use `domcontentloaded` plus explicit UI or stream assertions. Do not wait for `networkidle`.
- Prefer a non-mutating or intentionally rejected probe for repeated live smoke checks when successful requests would create junk state, consume quotas, or trigger throttles.
- Capture the acceptance states at realistic desktop and mobile sizes, then visually inspect the images. Filenames and successful screenshot commands are not visual proof.
- Assert sensitive names and values are absent from public wallboards, streams, error pages, and page source where applicable.

## Record the receipt

Record the public template ID, code, status, and URL; source tag and commit; project, environment, service, volume, and deployment IDs; public demo URL; PostgreSQL identity; lifecycle operations; smoke timestamp; and validation results. Never record resolved credentials.
