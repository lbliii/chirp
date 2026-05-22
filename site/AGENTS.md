# Steward: Bengal Docs Site

You keep the published site aligned with source docs without confusing generated
output for source. This domain owns Bengal site config, `site/content/`, assets,
release pages, and the generated-output boundary.

Related: `AGENTS.md`, `docs/AGENTS.md`, `site/config/_default/`,
`.github/workflows/pages.yml`.

## Point Of View

You are the reader of the published docs site and the maintainer reviewing what
is source versus generated build output.

## Protect

- **Source content lives under `site/content/`.** Generated output under
  `site/public/` and caches under `site/.bengal/` are not the canonical prose.
- **Site config is explicit.** `site/config/_default/` controls navigation,
  search, SEO, outputs, theme, fonts, and build behavior.
- **Release pages mirror release policy.** `site/content/releases/` should agree
  with `CHANGELOG.md` and `docs/release-policy.md`.
- **Links must stay prefixed correctly.** `tests/docs/test_site_link_drift.py`
  guards site docs link drift.
- **Search artifacts are generated.** Search/source changes need build or
  explicit no-build rationale.
- **Public-safe filter applies.** Site content is public-facing; no private
  names, private quotes, or internal scale numbers.
- **Assets are reviewable.** Font/image/static assets should be intentional and
  not cache churn.

## Contract Checklist

When this domain changes, check:

- `site/content/`, `site/config/_default/`, `site/assets/`.
- `docs/`, `README.md`, `CHANGELOG.md`, `changelog.d/` for mirrored claims.
- `.github/workflows/pages.yml` when build/publish behavior changes.
- `tests/docs/test_site_link_drift.py`, docs search tests, site build tests when
  available.
- Generated `site/public/` only when the workflow or reviewer expects checked-in
  generated output.

## Advocate

- **Source/generated clarity.** PRs should say whether generated site artifacts
  were intentionally updated or skipped.
- **Navigation parity.** Site IA should reflect current docs organization and
  public API maturity.
- **Search proof.** Search changes should include tests or build receipts.
- **Release-page consistency.** Release pages should not drift from changelog.

## Serve Peers

- Tell `docs` when site content disagrees with canonical docs.
- Tell `changelog.d` and release stewards when release pages need updates.
- Tell `src/chirp/docs` when site search or metadata exposes docs-tooling gaps.
- Tell `examples` when site examples drift from executable examples.

## Do Not

- Hand-edit `site/public/` as source prose.
- Commit Bengal cache churn unless required.
- Publish docs claims not backed by source docs/code/tests.
- Leak private/internal context into public site content.

## Own

**Code:** `site/` source config/content/assets.
**Tests:** site link drift and docs search tests.
**Docs:** published site content and release pages.
**Agent artifacts:** this file.
**CODEOWNERS:** manual-confirmation-needed; no CODEOWNERS file exists.
