**CI coverage gate enforced** — the main test job now runs pytest with `--cov`, so the `fail_under` threshold configured in `pyproject.toml` actually fails the build instead of being decorative.
