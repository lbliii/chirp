"""Tests for chirp.config — AppConfig frozen dataclass."""

import os
import warnings
from pathlib import Path

import pytest

from chirp.config import AppConfig

_ENV_KEYS_TO_CLEAR = ("PORT", "RAILWAY_ENVIRONMENT_ID", "RAILWAY_PUBLIC_DOMAIN")


def _pop_app_env() -> dict[str, str]:
    keys = [
        k for k in os.environ if k.startswith(("CHIRP_", "RAILWAY_")) or k in _ENV_KEYS_TO_CLEAR
    ]
    return {k: os.environ.pop(k) for k in keys}


def _app_env_keys() -> list[str]:
    return [
        k for k in os.environ if k.startswith(("CHIRP_", "RAILWAY_")) or k in _ENV_KEYS_TO_CLEAR
    ]


@pytest.fixture(autouse=True)
def _isolate_app_env():
    """Fully restore CHIRP_*/RAILWAY_* env around every test in this module.

    The per-test ``finally: os.environ.update(env_backup)`` blocks restore keys
    that pre-existed but never DELETE keys a test newly set (CHIRP_DEBUG,
    CHIRP_ENV, ...). Those leak into later tests in the same process — most
    visibly the Lucky Cat example, whose ``AppConfig.from_env()`` then reads
    debug=True + env='production' and ``app.check()`` raises SystemExit (this is
    why the full ``test`` job has been red since the example landed). Snapshot
    here and remove-then-restore on teardown so no test in this file can leak.
    """
    backup = {k: os.environ[k] for k in _app_env_keys()}
    try:
        yield
    finally:
        for k in _app_env_keys():
            del os.environ[k]
        os.environ.update(backup)


class TestAppConfig:
    def test_defaults(self) -> None:
        cfg = AppConfig()

        assert cfg.host == "127.0.0.1"
        assert cfg.port == 8000
        assert cfg.debug is False
        assert cfg.secret_key == ""
        assert cfg.template_dir == "templates"
        assert cfg.autoescape is True
        assert cfg.static_dir == "static"
        assert cfg.static_url == "/static"
        assert cfg.sse_heartbeat_interval == 15.0
        assert cfg.mcp_path == "/mcp"
        assert cfg.max_request_body_size == 16 * 1024 * 1024
        assert cfg.max_upload_size == 16 * 1024 * 1024
        assert cfg.view_transitions is False
        assert cfg.static_context is None
        assert cfg.display is None

    @pytest.mark.issue(699)
    def test_redis_url_is_redacted_from_repr(self) -> None:
        cfg = AppConfig(
            redis_url="redis://user:password@private.example/0",
            secret_key="private-secret",
        )
        assert "redis://" not in repr(cfg)
        assert "password" not in repr(cfg)
        assert "private-secret" not in repr(cfg)

    def test_production_proxy_and_rate_limit_defaults(self) -> None:
        cfg = AppConfig()

        assert cfg.rate_limit_max_tracked_ips == 100_000
        assert cfg.forwarded_for_trusted_hops == 1
        assert cfg.trusted_proxies == ()

    def test_production_proxy_and_rate_limit_override(self) -> None:
        cfg = AppConfig(
            rate_limit_max_tracked_ips=5_000,
            forwarded_for_trusted_hops=2,
            trusted_proxies=("10.0.0.1",),
        )

        assert cfg.rate_limit_max_tracked_ips == 5_000
        assert cfg.forwarded_for_trusted_hops == 2
        assert cfg.trusted_proxies == ("10.0.0.1",)

    def test_forwarded_for_trusted_hops_below_one_raises(self) -> None:
        """< 1 fails fast at construction (pounce rejects it at launch)."""
        from chirp.errors import ConfigurationError

        with pytest.raises(ConfigurationError, match="forwarded_for_trusted_hops"):
            AppConfig(forwarded_for_trusted_hops=0)

    def test_rate_limit_max_tracked_ips_has_no_env_parity(self) -> None:
        """rate_limit_max_tracked_ips is AppConfig-kwarg-only.

        ``from_env`` deliberately does not wire it (no matching CHIRP_* suffix),
        so an env-only construction leaves it at its default. Setting the
        unrecognized suffix also trips the unknown-env-var warning, which this
        asserts still fires for this name.
        """
        saved = _pop_app_env()
        try:
            os.environ["CHIRP_RATE_LIMIT_MAX_TRACKED_IPS"] = "7"
            with pytest.warns(UserWarning, match="Unknown env var"):
                cfg = AppConfig.from_env()
            # No env wiring → default retained.
            assert cfg.rate_limit_max_tracked_ips == 100_000
        finally:
            os.environ.pop("CHIRP_RATE_LIMIT_MAX_TRACKED_IPS", None)
            os.environ.update(saved)

    def test_forwarded_for_trusted_hops_env_parity(self) -> None:
        """CHIRP_FORWARDED_FOR_TRUSTED_HOPS is recognized and read (no warning)."""
        saved = _pop_app_env()
        try:
            os.environ["CHIRP_FORWARDED_FOR_TRUSTED_HOPS"] = "9"
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("error", UserWarning)
                cfg = AppConfig.from_env()
            assert cfg.forwarded_for_trusted_hops == 9
        finally:
            os.environ.pop("CHIRP_FORWARDED_FOR_TRUSTED_HOPS", None)
            os.environ.update(saved)

    def test_trusted_proxies_env_parity(self) -> None:
        """CHIRP_TRUSTED_PROXIES parses comma/space-separated peers (no warning)."""
        saved = _pop_app_env()
        try:
            os.environ["CHIRP_TRUSTED_PROXIES"] = "10.0.0.1, 10.0.0.2"
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("error", UserWarning)
                cfg = AppConfig.from_env()
            assert cfg.trusted_proxies == ("10.0.0.1", "10.0.0.2")
        finally:
            os.environ.pop("CHIRP_TRUSTED_PROXIES", None)
            os.environ.update(saved)

    def test_proxy_env_unset_defaults(self) -> None:
        """Unset proxy env vars leave trusted_proxies=() and hops=1."""
        saved = _pop_app_env()
        try:
            cfg = AppConfig.from_env()
            assert cfg.trusted_proxies == ()
            assert cfg.forwarded_for_trusted_hops == 1
        finally:
            os.environ.update(saved)

    def test_health_ready_path_defaults(self) -> None:
        """health_path/ready_path default to /health and /ready."""
        cfg = AppConfig()
        assert cfg.health_path == "/health"
        assert cfg.ready_path == "/ready"

    def test_health_ready_path_env_parity(self) -> None:
        """CHIRP_HEALTH_PATH / CHIRP_READY_PATH are recognized (no unknown-env warning)."""
        saved = _pop_app_env()
        try:
            os.environ["CHIRP_HEALTH_PATH"] = "/healthz"
            os.environ["CHIRP_READY_PATH"] = "/readyz"
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("error", UserWarning)
                cfg = AppConfig.from_env()
            assert cfg.health_path == "/healthz"
            assert cfg.ready_path == "/readyz"
        finally:
            os.environ.pop("CHIRP_HEALTH_PATH", None)
            os.environ.pop("CHIRP_READY_PATH", None)
            os.environ.update(saved)

    def test_health_ready_path_env_unset_defaults(self) -> None:
        """Unset probe env vars leave the /health + /ready defaults."""
        saved = _pop_app_env()
        try:
            cfg = AppConfig.from_env()
            assert cfg.health_path == "/health"
            assert cfg.ready_path == "/ready"
        finally:
            os.environ.update(saved)

    def test_override(self) -> None:
        cfg = AppConfig(host="0.0.0.0", port=3000, debug=True, secret_key="s3cret")

        assert cfg.host == "0.0.0.0"
        assert cfg.port == 3000
        assert cfg.debug is True
        assert cfg.secret_key == "s3cret"

    def test_frozen(self) -> None:
        cfg = AppConfig()

        with pytest.raises(AttributeError):
            cfg.debug = True  # type: ignore[misc]

    def test_upload_cap_exceeding_body_cap_raises(self) -> None:
        from chirp.errors import ConfigurationError

        with pytest.raises(ConfigurationError, match="max_upload_size"):
            AppConfig(max_request_body_size=100, max_upload_size=1000)

    def test_static_context_frozen_to_mapping_proxy(self) -> None:
        cfg = AppConfig(static_context={"site": "Chirp"})
        from types import MappingProxyType

        assert isinstance(cfg.static_context, MappingProxyType)
        assert cfg.static_context["site"] == "Chirp"
        with pytest.raises(TypeError):
            cfg.static_context["site"] = "changed"  # type: ignore[index]

    def test_template_dir_as_path(self) -> None:
        cfg = AppConfig(template_dir=Path("views"))
        assert cfg.template_dir == Path("views")

    def test_static_dir_none(self) -> None:
        cfg = AppConfig(static_dir=None)
        assert cfg.static_dir is None

    def test_reload_include_default(self) -> None:
        cfg = AppConfig()
        assert cfg.reload_include == (".html", ".css", ".md")

    def test_reload_include_opt_out(self) -> None:
        cfg = AppConfig(reload_include=())
        assert cfg.reload_include == ()

    def test_reload_dirs_default(self) -> None:
        cfg = AppConfig()
        assert cfg.reload_dirs == ()

    def test_reload_include_custom(self) -> None:
        cfg = AppConfig(reload_include=(".html", ".css", ".md"))
        assert cfg.reload_include == (".html", ".css", ".md")

    def test_reload_dirs_custom(self) -> None:
        cfg = AppConfig(reload_dirs=("./templates", "./static"))
        assert cfg.reload_dirs == ("./templates", "./static")

    def test_alpine_defaults(self) -> None:
        cfg = AppConfig()
        assert cfg.alpine is False
        assert cfg.alpine_version == "3.15.8"
        assert cfg.alpine_csp is False

    def test_alpine_enabled(self) -> None:
        cfg = AppConfig(alpine=True)
        assert cfg.alpine is True

    def test_alpine_version_override(self) -> None:
        cfg = AppConfig(alpine=True, alpine_version="3.14.0")
        assert cfg.alpine_version == "3.14.0"

    def test_alpine_csp(self) -> None:
        cfg = AppConfig(alpine=True, alpine_csp=True)
        assert cfg.alpine_csp is True

    def test_from_env_defaults(self) -> None:
        """from_env uses defaults when env is empty."""
        # Clear chirp-related env to avoid leakage from test runner
        env_backup = _pop_app_env()
        try:
            cfg = AppConfig.from_env()
            assert cfg.host == "127.0.0.1"
            assert cfg.port == 8000
            assert cfg.debug is False
            assert cfg.env == "development"
            assert cfg.redis_url is None
            assert cfg.http_timeout == 30.0
            assert cfg.http_retries == 0
            assert cfg.log_format == "auto"
        finally:
            os.environ.update(env_backup)

    def test_from_env_overrides(self) -> None:
        """from_env reads CHIRP_* env vars."""
        env_backup = _pop_app_env()
        try:
            os.environ["CHIRP_HOST"] = "0.0.0.0"
            os.environ["CHIRP_PORT"] = "3000"
            os.environ["CHIRP_DEBUG"] = "true"
            os.environ["CHIRP_SECRET_KEY"] = "from-env"
            os.environ["CHIRP_ENV"] = "production"
            os.environ["CHIRP_REDIS_URL"] = "redis://localhost"
            os.environ["CHIRP_HTTP_TIMEOUT"] = "60"
            os.environ["CHIRP_HTTP_RETRIES"] = "3"
            os.environ["CHIRP_LOG_FORMAT"] = "json"
            os.environ["CHIRP_ALLOWED_HOSTS"] = "example.com,.example.com"
            cfg = AppConfig.from_env()
            assert cfg.host == "0.0.0.0"
            assert cfg.port == 3000
            assert cfg.debug is True
            assert cfg.secret_key == "from-env"
            assert cfg.env == "production"
            assert cfg.redis_url == "redis://localhost"
            assert cfg.http_timeout == 60.0
            assert cfg.http_retries == 3
            assert cfg.log_format == "json"
            assert cfg.allowed_hosts == ("example.com", ".example.com")
        finally:
            os.environ.update(env_backup)

    def test_skip_migrations_default_false(self) -> None:
        """skip_migrations defaults False, mirroring skip_contract_checks."""
        cfg = AppConfig()
        assert cfg.skip_migrations is False

    def test_skip_migrations_env_parity(self) -> None:
        """CHIRP_SKIP_MIGRATIONS=1 sets skip_migrations via from_env()."""
        env_backup = _pop_app_env()
        try:
            os.environ["CHIRP_SKIP_MIGRATIONS"] = "1"
            cfg = AppConfig.from_env()
            assert cfg.skip_migrations is True
        finally:
            os.environ.update(env_backup)

    def test_skip_migrations_env_unset_defaults_false(self) -> None:
        """from_env() leaves skip_migrations False when the env var is unset."""
        env_backup = _pop_app_env()
        try:
            cfg = AppConfig.from_env()
            assert cfg.skip_migrations is False
        finally:
            os.environ.update(env_backup)

    def test_skip_migrations_no_unknown_env_warning(self) -> None:
        """CHIRP_SKIP_MIGRATIONS is on the known-suffix allowlist (no warning)."""
        env_backup = _pop_app_env()
        try:
            os.environ["CHIRP_SKIP_MIGRATIONS"] = "1"
            with warnings.catch_warnings():
                warnings.simplefilter("error", UserWarning)
                AppConfig.from_env()
        finally:
            os.environ.update(env_backup)

    def test_from_env_railway_port_host_and_healthcheck_hosts(self) -> None:
        env_backup = _pop_app_env()
        try:
            os.environ["PORT"] = "4732"
            os.environ["RAILWAY_ENVIRONMENT_ID"] = "env_123"
            os.environ["RAILWAY_PUBLIC_DOMAIN"] = "forum.example.up.railway.app"
            cfg = AppConfig.from_env()
            assert cfg.host == "0.0.0.0"
            assert cfg.port == 4732
            assert cfg.allowed_hosts == (
                "forum.example.up.railway.app",
                "healthcheck.railway.app",
            )
        finally:
            os.environ.update(env_backup)

    def test_from_env_chirp_port_and_hosts_override_railway_defaults(self) -> None:
        env_backup = _pop_app_env()
        try:
            os.environ["PORT"] = "4732"
            os.environ["CHIRP_PORT"] = "9000"
            os.environ["CHIRP_HOST"] = "127.0.0.1"
            os.environ["CHIRP_ALLOWED_HOSTS"] = "forum.example.com healthcheck.railway.app"
            os.environ["RAILWAY_ENVIRONMENT_ID"] = "env_123"
            os.environ["RAILWAY_PUBLIC_DOMAIN"] = "forum.example.up.railway.app"
            cfg = AppConfig.from_env()
            assert cfg.host == "127.0.0.1"
            assert cfg.port == 9000
            assert cfg.allowed_hosts == ("forum.example.com", "healthcheck.railway.app")
        finally:
            os.environ.update(env_backup)

    def test_from_env_invalid_log_format_ignored(self) -> None:
        """Invalid CHIRP_LOG_FORMAT falls back to default."""
        env_backup = _pop_app_env()
        try:
            os.environ["CHIRP_LOG_FORMAT"] = "xml"
            cfg = AppConfig.from_env()
            assert cfg.log_format == "auto"
        finally:
            os.environ.update(env_backup)

    def test_from_env_log_level(self) -> None:
        """CHIRP_LOG_LEVEL maps onto the existing log_level field (env parity)."""
        env_backup = _pop_app_env()
        try:
            os.environ["CHIRP_LOG_LEVEL"] = "debug"
            cfg = AppConfig.from_env()
            assert cfg.log_level == "debug"
        finally:
            os.environ.update(env_backup)

    def test_from_env_invalid_log_level_ignored(self) -> None:
        """Invalid CHIRP_LOG_LEVEL falls back to the default ('info')."""
        env_backup = _pop_app_env()
        try:
            os.environ["CHIRP_LOG_LEVEL"] = "trace"
            cfg = AppConfig.from_env()
            assert cfg.log_level == "info"
        finally:
            os.environ.update(env_backup)

    def test_invalid_view_transitions_raises(self) -> None:
        with pytest.raises(ValueError, match="view_transitions"):
            AppConfig(view_transitions="bad")

    def test_invalid_speculation_rules_raises(self) -> None:
        with pytest.raises(ValueError, match="speculation_rules"):
            AppConfig(speculation_rules="bad")

    def test_valid_view_transitions_accepted(self) -> None:
        for val in (False, True, "off", "htmx", "full"):
            cfg = AppConfig(view_transitions=val)
            assert cfg.view_transitions == val

    def test_valid_speculation_rules_accepted(self) -> None:
        for val in (False, True, "off", "conservative", "moderate", "eager"):
            cfg = AppConfig(speculation_rules=val)
            assert cfg.speculation_rules == val

    def test_from_env_feature_flags(self) -> None:
        """from_env parses CHIRP_FEATURE_* vars."""
        env_backup = _pop_app_env()
        try:
            os.environ["CHIRP_FEATURE_X"] = "true"
            os.environ["CHIRP_FEATURE_Y"] = "false"
            cfg = AppConfig.from_env()
            assert cfg.feature("x") is True
            assert cfg.feature("y") is False
            assert cfg.feature("z") is False
        finally:
            os.environ.update(env_backup)

    @pytest.mark.issue(237)
    def test_from_env_kwargs_override(self) -> None:
        """from_env(**overrides) applies kwargs after env loading."""
        env_backup = _pop_app_env()
        try:
            os.environ["CHIRP_DEBUG"] = "false"
            cfg = AppConfig.from_env(
                template_dir="pages",
                worker_mode="async",
                debug=True,
            )
            assert cfg.template_dir == "pages"
            assert cfg.worker_mode == "async"
            assert cfg.debug is True
        finally:
            os.environ.update(env_backup)
