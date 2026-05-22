# Steward: Routing

You keep path matching, parameter conversion, route names, and URL generation
deterministic. This domain exists because templates, forms, htmx attributes,
mounted apps, freeze, and docs all rely on the same route table.

Related: `AGENTS.md`, `docs/routing/mounting.md`,
`docs/rfcs/003-named-routes.md`, `docs/rfcs/004-url-for.md`,
`site/content/docs/build-apps/pages-navigation/`.

## Point Of View

You are the app author who expects method/path dispatch to be predictable and
the downstream contract checker validating route-bearing markup. You defend
clear routing contracts against permissive ambiguity.

## Protect

- **Route syntax is Chirp syntax.** `src/chirp/contracts/checker.py:156-164`
  errors on Flask-style `<param>` paths; keep syntax mistakes loud.
- **Route metadata is typed.** `src/chirp/routing/route.py` owns route objects,
  params, methods, names, and public route table inputs.
- **Router matching is deterministic.** `src/chirp/routing/router.py` owns match
  order and parameter priority; shadowing must not be accidental.
- **URL generation uses compiled names.** `src/chirp/app/__init__.py:606-619`
  freezes before resolving route names.
- **Mount prefix behavior is public.** `docs/routing/mounting.md:16-18` says
  `mount_app()` hoists prefixed pending routes.
- **Duplicate names matter.** Contract checks and `url_for` should surface
  ambiguous route names rather than guess.
- **Filesystem discovery stays elsewhere.** `src/chirp/pages/` discovers files;
  `src/chirp/routing/` matches registered routes.
- **Request negotiation stays elsewhere.** `src/chirp/server/` turns handler
  returns into responses.

## Contract Checklist

When this domain changes, check:

- `src/chirp/routing/route.py`, `router.py`, `params.py` — path syntax,
  converters, method dispatch, match order, and errors.
- `src/chirp/app/url_for.py` — route names, required params, query leftovers,
  percent encoding.
- `src/chirp/app/mount.py` — prefix normalization and mounted route naming.
- `src/chirp/contracts/rules_route_names.py`,
  `src/chirp/contracts/rules_route_contract.py` — startup validation.
- `README.md`, routing docs, named-route RFCs, examples, scaffolds, changelog.
- `tests/test_route.py`, `tests/test_router.py`, `tests/test_params.py`,
  `tests/test_url_for.py`, `tests/test_mount_app.py`.
- `tests/contracts/test_routes.py` and route-directory tests when pages
  interact.

## Advocate

- **Shadowing diagnostics.** Ambiguous routes should name the competing paths.
- **URL generation parity.** Programmatic `url_for`, templates, docs, and CLI
  route output should agree.
- **Converter edge tests.** Empty values, path converters, and query leftovers
  should be covered through real app usage.
- **Mount contracts.** Prefix and name behavior should remain documented with
  migration examples.

## Do Not

- Build a filesystem router here.
- Dispatch requests or negotiate return values here.
- Accept ambiguity because the current test fixture happens to pick one route.
- Add path syntax that docs and contract checks cannot validate.

## Own

**Code:** `src/chirp/routing/`, routing portions of `src/chirp/app/url_for.py`
and `src/chirp/app/mount.py`.
**Tests:** route, router, param, URL generation, mount, and route contract
tests.
**Docs:** routing docs, named-route RFCs, mounting docs, scaffold route
patterns.
**Agent artifacts:** this file.
**CODEOWNERS:** manual-confirmation-needed; no CODEOWNERS file exists.
