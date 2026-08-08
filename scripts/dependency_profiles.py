"""Supported dependency resolution profiles (decision #908 / issue #910).

This module is the machine-readable matrix consumed by ``install_smoke.py`` and
the ``install-smoke`` GitHub Actions workflow. Profile IDs and resolution paths
must stay aligned with
``plan/drafted/decision-908-dependency-resolution-profiles.md``.

Adding a profile requires a new decision leaf — do not expand this matrix in
implementation PRs alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Primary Chirp posture is free-threaded 3.14t; GIL 3.14 is covered where the
# decision calls for required Python variants.
PythonKind = Literal["3.14", "3.14t"]


@dataclass(frozen=True, slots=True)
class DependencyProfile:
    """One supported install + import-smoke surface."""

    id: str
    purpose: str
    # Human-readable resolution path named in failure output (canonical install).
    resolution: str
    # Args appended to ``uv sync --no-sources`` for an isolated project env.
    # Consumer profiles always pass ``--no-dev`` so the default ``dev`` group
    # does not leak into minimal / extra / full / all smokes.
    sync_args: tuple[str, ...]
    # Modules that must import after install (import smoke only — not behavior).
    import_modules: tuple[str, ...]
    # Extra Python statements executed after the imports (assertions allowed).
    smoke_statements: tuple[str, ...] = ()
    # Optional ``uv pip install ...`` args run after sync (compat pins).
    post_pip_args: tuple[str, ...] = ()
    # Python builds that must prove this profile in CI.
    python: tuple[PythonKind, ...] = ("3.14t",)


# Canonical matrix from decision #908. Keep IDs stable — CI job names and
# failure messages key on them.
SUPPORTED_PROFILES: tuple[DependencyProfile, ...] = (
    DependencyProfile(
        id="minimal",
        purpose="End-user core framework only",
        resolution="uv sync --no-sources --no-dev  (same as: uv add bengal-chirp)",
        sync_args=("--no-dev",),
        import_modules=("chirp",),
        smoke_statements=("assert chirp.__version__",),
        python=("3.14", "3.14t"),
    ),
    DependencyProfile(
        id="dev",
        purpose="Ordinary contributor + default CI",
        resolution="uv sync --no-sources --group dev",
        sync_args=("--group", "dev"),
        import_modules=(
            "chirp",
            "pytest",
            "httpx",
            "multipart",
            "itsdangerous",
            "patitas",
            "chirp_ui",
        ),
        python=("3.14", "3.14t"),
    ),
    DependencyProfile(
        id="docs",
        purpose="Bengal docs site build",
        resolution="uv sync --no-sources --group docs",
        sync_args=("--group", "docs"),
        import_modules=("bengal", "chirp_ui"),
    ),
    DependencyProfile(
        id="browser",
        purpose="Playwright browser smoke dependencies",
        resolution="uv sync --no-sources --group dev --group browser",
        sync_args=("--group", "dev", "--group", "browser"),
        import_modules=("playwright",),
    ),
    DependencyProfile(
        id="benchmark",
        purpose="Framework comparison suite",
        resolution="uv sync --no-sources --no-dev --extra benchmark",
        sync_args=("--no-dev", "--extra", "benchmark"),
        import_modules=("fastapi", "flask", "starlette", "litestar", "httpx"),
    ),
    DependencyProfile(
        id="full",
        purpose='Aggregate "common optional stack" alias',
        resolution="uv sync --no-sources --no-dev --extra full  (same as: bengal-chirp[full])",
        sync_args=("--no-dev", "--extra", "full"),
        import_modules=("chirp", "multipart", "itsdangerous", "argon2", "httpx", "patitas"),
    ),
    DependencyProfile(
        id="all",
        purpose="Documented synonym of full (identical contents)",
        resolution="uv sync --no-sources --no-dev --extra all  (same as: bengal-chirp[all])",
        sync_args=("--no-dev", "--extra", "all"),
        import_modules=("chirp", "multipart", "itsdangerous", "argon2", "httpx", "patitas"),
    ),
    DependencyProfile(
        id="extra-forms",
        purpose="Multipart form parsing",
        resolution="uv sync --no-sources --no-dev --extra forms  (same as: bengal-chirp[forms])",
        sync_args=("--no-dev", "--extra", "forms"),
        import_modules=("chirp", "multipart"),
    ),
    DependencyProfile(
        id="extra-sessions",
        purpose="Signed cookie sessions",
        resolution="uv sync --no-sources --no-dev --extra sessions",
        sync_args=("--no-dev", "--extra", "sessions"),
        import_modules=("chirp", "itsdangerous"),
    ),
    DependencyProfile(
        id="extra-auth",
        purpose="Argon2 password hashing",
        resolution="uv sync --no-sources --no-dev --extra auth",
        sync_args=("--no-dev", "--extra", "auth"),
        import_modules=("chirp", "argon2"),
    ),
    DependencyProfile(
        id="extra-passkeys",
        purpose="WebAuthn / passkeys",
        resolution="uv sync --no-sources --no-dev --extra passkeys",
        sync_args=("--no-dev", "--extra", "passkeys"),
        import_modules=("chirp", "webauthn"),
    ),
    DependencyProfile(
        id="extra-testing",
        purpose="httpx test-client transport",
        resolution="uv sync --no-sources --no-dev --extra testing",
        sync_args=("--no-dev", "--extra", "testing"),
        import_modules=("chirp", "httpx"),
    ),
    DependencyProfile(
        id="extra-data-pg",
        purpose="PostgreSQL via in-tree pelt (no PyPI deps)",
        resolution="uv sync --no-sources --no-dev --extra data-pg",
        sync_args=("--no-dev", "--extra", "data-pg"),
        import_modules=("chirp", "chirp.data.drivers._pelt"),
    ),
    DependencyProfile(
        id="extra-ai",
        purpose="LLM streaming over raw HTTP",
        resolution="uv sync --no-sources --no-dev --extra ai",
        sync_args=("--no-dev", "--extra", "ai"),
        import_modules=("chirp", "httpx", "chirp.ai"),
    ),
    DependencyProfile(
        id="extra-ai-bedrock",
        purpose="AWS Bedrock signing",
        resolution="uv sync --no-sources --no-dev --extra ai-bedrock",
        sync_args=("--no-dev", "--extra", "ai-bedrock"),
        import_modules=("chirp", "botocore", "httpx"),
    ),
    DependencyProfile(
        id="extra-markdown",
        purpose="Patitas markdown rendering",
        resolution="uv sync --no-sources --no-dev --extra markdown",
        sync_args=("--no-dev", "--extra", "markdown"),
        import_modules=("chirp", "patitas"),
    ),
    DependencyProfile(
        id="extra-ui",
        purpose="Install chirp-ui via Chirp extra",
        resolution="uv sync --no-sources --no-dev --extra ui",
        sync_args=("--no-dev", "--extra", "ui"),
        import_modules=("chirp", "chirp_ui"),
    ),
    DependencyProfile(
        id="extra-config",
        purpose="python-dotenv for AppConfig.from_env()",
        resolution="uv sync --no-sources --no-dev --extra config",
        sync_args=("--no-dev", "--extra", "config"),
        import_modules=("chirp", "dotenv"),
    ),
    DependencyProfile(
        id="extra-redis",
        purpose="Redis sessions / rate limit / signal backplane",
        resolution="uv sync --no-sources --no-dev --extra redis",
        sync_args=("--no-dev", "--extra", "redis"),
        import_modules=("chirp", "redis"),
    ),
    DependencyProfile(
        id="chirp-ui-compat",
        purpose="Cross-version Chirp ↔ chirp-ui compatibility (floor pin)",
        resolution=(
            "uv sync --no-sources --group dev --extra ui && uv pip install chirp-ui==0.10.0"
        ),
        sync_args=("--group", "dev", "--extra", "ui"),
        # Floor pin from decision #908; unpinned latest is covered by extra-ui/dev.
        post_pip_args=("chirp-ui==0.10.0",),
        import_modules=("chirp", "chirp_ui"),
    ),
)


PROFILE_BY_ID: dict[str, DependencyProfile] = {p.id: p for p in SUPPORTED_PROFILES}


def ci_matrix_entries() -> list[dict[str, str]]:
    """Expand profiles x python kinds for the install-smoke workflow matrix."""
    entries: list[dict[str, str]] = []
    for profile in SUPPORTED_PROFILES:
        entries.extend(
            {
                "profile": profile.id,
                "python-version": py,
                "free_threaded": "true" if py.endswith("t") else "false",
            }
            for py in profile.python
        )
    return entries
