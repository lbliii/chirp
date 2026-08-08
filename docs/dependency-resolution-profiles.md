# Dependency resolution profiles

Maintained consumer surface for the supported dependency resolution matrix
defined by [decision #908](../plan/drafted/decision-908-dependency-resolution-profiles.md)
(parent epic [#899](https://github.com/lbliii/chirp/issues/899)).

Chirp supports a **finite** set of named profiles. Profiles are not a Cartesian
product of extras × groups × Python builds. Adding a profile requires a new
decision leaf.

## Fresh-environment proof (#910)

Every supported profile is proven in a clean environment by:

- **CI:** `.github/workflows/install-smoke.yml` (dedicated job; does not bloat
  Redis / skip-fail / auth / browser / Postgres capability lanes).
- **Local command:**

```bash
python scripts/install_smoke.py --list
python scripts/install_smoke.py --profile minimal --python 3.14t
python scripts/install_smoke.py --all --python 3.14t
```

Failures name the **profile ID** and the **resolution path** (the `uv sync` /
pin command for that profile). Import smoke only proves the intended surface is
loadable — it does not replace behavioral integration tests.

Python variants: free-threaded `3.14t` for every profile; GIL `3.14` additionally
for `minimal` and `dev`.

## Supported profile IDs

| Profile | Purpose (short) | Resolution (in-repo) |
| --- | --- | --- |
| `minimal` | Core framework only | `uv sync --no-sources --no-dev` |
| `dev` | Ordinary contributor / default CI | `uv sync --no-sources --group dev` |
| `docs` | Docs site build | `uv sync --no-sources --group docs` |
| `browser` | Playwright deps | `uv sync --no-sources --group dev --group browser` |
| `benchmark` | Framework comparison extra | `uv sync --no-sources --no-dev --extra benchmark` |
| `full` / `all` | Common optional stack aliases | `--extra full` / `--extra all` |
| `extra-forms` … `extra-redis` | Single optional extras | `--no-dev --extra <name>` |
| `chirp-ui-compat` | Chirp UI floor pin (`0.10.0`) | `--group dev --extra ui` then pin |

Machine-readable source of truth: `scripts/dependency_profiles.py`.

## Ordinary contributor setup

Keep day-to-day setup small:

```bash
uv sync --group dev
```

Do **not** run the full profile matrix as part of normal local development.
Use `install-smoke` in CI or the explicit script above when verifying resolution.
