"""Declared skip policy for specialized CI capability lanes (#917).

Each specialized ``ci.yml`` job that proves an optional capability or
infrastructure dependency opts in with ``CHIRP_CAPABILITY_LANE=<name>``. The
pytest plugin then:

1. Asserts each ``required_selectors`` substring matches at least one collected
   node id (catches missing collection / importorskip of a whole module).
2. Fails the session on any skip whose reason does not contain an
   ``allowed_skip_reason_substrings`` entry (catches env/service regressions).

The default unit job and ordinary local runs leave the env unset, so optional
dependency skips remain soft skips outside specialized lanes.
"""

from __future__ import annotations

from dataclasses import dataclass

CAPABILITY_LANE_ENV = "CHIRP_CAPABILITY_LANE"


@dataclass(frozen=True, slots=True)
class CapabilityLane:
    """Skip / collection policy for one specialized CI pytest invocation."""

    name: str
    """Value of ``CHIRP_CAPABILITY_LANE`` and the owning CI job id (or step)."""

    capability: str
    """Human-readable capability or infrastructure this lane proves."""

    install_hint: str
    """Actionable profile / service guidance for failure diagnostics."""

    required_selectors: tuple[str, ...]
    """Each substring must appear in at least one collected item node id."""

    allowed_skip_reason_substrings: tuple[str, ...] = ()
    """Skip reasons containing any of these substrings are intentional."""


def get_lane(name: str) -> CapabilityLane:
    """Return a registered lane or raise ``KeyError`` with known names."""
    try:
        return LANE_REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(LANE_REGISTRY)) or "(none)"
        raise KeyError(f"unknown capability lane {name!r}; known lanes: {known}") from None


# ---------------------------------------------------------------------------
# Registry — add new specialized lanes here (e.g. redis-capability / #906).
# ---------------------------------------------------------------------------

LANE_REGISTRY: dict[str, CapabilityLane] = {
    "auth-capability": CapabilityLane(
        name="auth-capability",
        capability="chirp[auth] / argon2-cffi (Argon2 password hashing)",
        install_hint=(
            "uv sync --group dev --extra auth; keep CHIRP_REQUIRE_ARGON2=1 "
            "on the auth-capability CI job"
        ),
        required_selectors=(
            "test_passwords.py::TestArgon2::",
            "test_passwords.py::TestArgon2FailClosed::",
            "contracts/test_password_extra.py",
        ),
    ),
    "redis-capability": CapabilityLane(
        name="redis-capability",
        capability="chirp[redis] + live Redis (sessions / cache / rate-limit)",
        install_hint=(
            "uv sync --group dev --extra redis; start Redis; set "
            "CHIRP_REQUIRE_REDIS=1 and CHIRP_TEST_REDIS_URL "
            "(see ci.yml redis-capability)"
        ),
        required_selectors=(
            "test_redis_capability.py::test_live_redis_session_roundtrip",
            "test_redis_capability.py::test_live_redis_cache_get_set",
            "test_redis_capability.py::test_unavailable_redis_session_save_fails_loudly",
            "test_passkey_session_stores.py::",
        ),
    ),
    "config-capability": CapabilityLane(
        name="config-capability",
        capability="chirp[config] / python-dotenv (.env via AppConfig.from_env)",
        install_hint=(
            "uv sync --group dev --extra config; keep CHIRP_REQUIRE_DOTENV=1 "
            "on the config-capability CI job"
        ),
        required_selectors=(
            "test_config_capability.py::test_from_env_loads_dotenv_file",
            "test_config_capability.py::test_from_env_process_env_wins_over_dotenv",
        ),
    ),
    "ai-bedrock-capability": CapabilityLane(
        name="ai-bedrock-capability",
        capability="chirp[ai-bedrock] / botocore (credential-free Bedrock signing)",
        install_hint=(
            "uv sync --group dev --extra ai-bedrock; keep "
            "CHIRP_REQUIRE_BOTOCORE=1 on the ai-bedrock-capability CI job"
        ),
        required_selectors=(
            "test_ai_bedrock_capability.py::test_bedrock_generate_signs_with_botocore",
            "test_ai/test_phase3.py::TestAdditionalProviders::test_bedrock_generate_requires_botocore",
        ),
    ),
    "browser-smoke": CapabilityLane(
        name="browser-smoke",
        capability="Playwright + Chromium (real-browser smoke)",
        install_hint=(
            "uv sync --group dev --group browser; uv run playwright install chromium --with-deps"
        ),
        required_selectors=(
            "lucky_cat/test_browser_smoke.py",
            "htmx_managed/test_browser_smoke.py",
        ),
    ),
    "query-interop": CapabilityLane(
        name="query-interop",
        capability="QUERY wire clients (H2/H3) + nginx reverse-proxy proof",
        install_hint=(
            "install bengal-pounce[h2,h3], httpx[http2], uvicorn, and nginx "
            "(see ci.yml query-interop job)"
        ),
        required_selectors=(
            "interop/test_query_wire.py",
            "test_nginx_reverse_proxy_preserves_query_method_and_body",
        ),
    ),
    "test-postgres": CapabilityLane(
        name="test-postgres",
        capability="live PostgreSQL (CHIRP_TEST_PG_* DSNs + TLS fixture)",
        install_hint=(
            "start Postgres; export CHIRP_TEST_PG_DSN / TLS DSN env vars; "
            "run scripts/setup-pelt-postgres-tls (see ci.yml test-postgres)"
        ),
        required_selectors=(
            "test_pelt/test_connection_integration.py::",
            "test_pelt/test_tls_auth_integration.py::",
            "test_jobs_postgres.py::",
            "test_schema_introspect.py::",
        ),
    ),
    "data-pg-gil-gate": CapabilityLane(
        name="data-pg-gil-gate",
        capability="free-threaded CPython + live PostgreSQL (data-pg GIL gate)",
        install_hint=(
            "use python-version 3.14t with PYTHON_GIL=0; export "
            "CHIRP_TEST_PG_DSN against a live Postgres service"
        ),
        required_selectors=(
            "test_pelt/test_data_pg_gil.py::",
            "test_parallel_row_decode_overlaps_on_native_threads",
            "test_jobs_postgres.py::",
        ),
    ),
    "chirp-ui-compat": CapabilityLane(
        name="chirp-ui-compat",
        capability="chirp-ui package (boundary + contract + compat CI wiring)",
        install_hint="uv sync --group dev --extra ui (and pin/upgrade chirp-ui)",
        required_selectors=(
            "test_chirpui_boundary.py::",
            "test_chirpui_compat_ci.py::",
            "contracts/test_custom_checks_integration.py::",
        ),
        allowed_skip_reason_substrings=(
            # Older chirp-ui matrix pins may omit the Alpine runtime asset.
            "chirp-ui Alpine runtime not available in this version",
        ),
    ),
    "chirp-ui-compat-shells": CapabilityLane(
        name="chirp-ui-compat-shells",
        capability="chirp-ui shell example smoke (contacts/forum/pages)",
        install_hint="uv sync --group dev --extra ui (and pin/upgrade chirp-ui)",
        required_selectors=(
            "examples/chirpui/contacts_shell",
            "examples/chirpui/forum_shell",
            "examples/chirpui/pages_shell",
        ),
    ),
}


def missing_required_selectors(
    lane: CapabilityLane, nodeids: list[str] | tuple[str, ...]
) -> list[str]:
    """Return required selectors that matched zero collected node ids."""
    return [
        selector
        for selector in lane.required_selectors
        if not any(selector in nodeid for nodeid in nodeids)
    ]


def is_allowed_skip(lane: CapabilityLane, reason: str) -> bool:
    """Return True when ``reason`` matches an intentional skip substring."""
    return any(allowed in reason for allowed in lane.allowed_skip_reason_substrings)


def format_collection_failure(lane: CapabilityLane, missing: list[str]) -> str:
    """Diagnostic when required selectors collected nothing."""
    missing_list = "\n".join(f"  - {selector!r}" for selector in missing)
    return (
        f"capability lane {lane.name!r}: required selectors collected zero tests:\n"
        f"{missing_list}\n"
        f"Missing capability/infrastructure: {lane.capability}\n"
        f"Install/service hint: {lane.install_hint}"
    )


def format_skip_failure(
    lane: CapabilityLane,
    unexpected: list[tuple[str, str]],
) -> str:
    """Diagnostic when required tests skipped unexpectedly."""
    lines = "\n".join(f"  - {nodeid}: {reason}" for nodeid, reason in unexpected)
    allowed = (
        ", ".join(repr(s) for s in lane.allowed_skip_reason_substrings)
        if lane.allowed_skip_reason_substrings
        else "(none — this lane forbids skips)"
    )
    return (
        f"capability lane {lane.name!r}: unexpected skips "
        f"({len(unexpected)}; required capability tests must not soft-skip):\n"
        f"{lines}\n"
        f"Missing capability/infrastructure: {lane.capability}\n"
        f"Install/service hint: {lane.install_hint}\n"
        f"Allowed skip reason substrings: {allowed}"
    )
