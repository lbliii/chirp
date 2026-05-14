"""Optional dependency contract checks."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FEATURE_EXTRAS = (
    "forms",
    "sessions",
    "auth",
    "testing",
    "data-pg",
    "ai",
    "markdown",
    "ui",
    "config",
    "redis",
)


def _optional_dependencies() -> dict[str, list[str]]:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return pyproject["project"]["optional-dependencies"]


def test_all_extra_contains_every_documented_feature_extra() -> None:
    """The ``all`` extra should not lag behind feature extras."""
    optional = _optional_dependencies()
    all_deps = set(optional["all"])

    missing: dict[str, list[str]] = {}
    for extra in FEATURE_EXTRAS:
        extra_deps = set(optional[extra])
        absent = sorted(extra_deps - all_deps)
        if absent:
            missing[extra] = absent

    assert not missing, (
        f"Add these feature extra dependencies to [project.optional-dependencies].all: {missing}"
    )


def test_sqlite_is_not_documented_as_a_data_extra() -> None:
    """SQLite uses stdlib sqlite3 plus anyio, so there is no ``data`` extra."""
    optional = _optional_dependencies()
    assert "data" not in optional

    install_doc = (
        ROOT / "site" / "content" / "docs" / "get-started" / "installation.md"
    ).read_text(encoding="utf-8")
    assert "bengal-chirp[data]" not in install_doc
