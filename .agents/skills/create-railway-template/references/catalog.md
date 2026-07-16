# Chirp Railway catalog integration

Update catalog collateral only after the public template passes clean deployment and product proof.

## Start from current catalog state

- Fetch the catalog's current default branch immediately before editing; its schema and source of truth may have changed during application work.
- Inspect the current repository instructions and authoritative catalog manifest. Use `catalog.json` when that repository identifies it as the source of truth; do not infer current entries from roadmap prose or old per-template files.
- Preserve unrelated catalog changes and rebase the focused branch before final validation.

## Keep every surface aligned

Update the template code, public URL, release tag, source commit, demo URL, category, description, overview, marketplace image, and latest successful smoke timestamp wherever the current catalog schema requires them. Keep the application repository README and dedicated marketplace overview consistent with the catalog.

Derive generated credentials from the manifest rather than from a hard-coded allowlist. Every variable declared as generated must:

1. have a Railway `secret(...)` generator in the serialized public template;
2. be supplied by catalog test and deployment runners without revealing the resolved value; and
3. appear in live zero-input conformance checks.

## Validate local and live behavior

- Run the catalog's formatter, linter, schema tests, and conformance suite from current main.
- Run every manifest-declared live check against the final deployment, including product transitions where the catalog supports them.
- Validate any operations receipt and ensure IDs, timestamps, URLs, and source revisions describe the final successful deployment rather than an earlier attempt.
- Re-run catalog checks after rebasing. A green result from a stale base is not final proof.
