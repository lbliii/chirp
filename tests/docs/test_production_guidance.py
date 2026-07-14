"""Guards for production deployment guidance."""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_PRODUCTION_DOCS = (
    _ROOT / "docs" / "deployment" / "production.md",
    _ROOT / "site" / "content" / "docs" / "quality" / "deployment" / "production.md",
)

_UNSUPPORTED_CHIRP_ENV_VARS = (
    "WORKERS=",
    "METRICS_ENABLED=",
    "RATE_LIMIT_ENABLED=",
    "RATE_LIMIT_RPS=",
    "QUEUE_ENABLED=",
    "QUEUE_MAX_DEPTH=",
)


def test_production_docs_do_not_imply_pounce_env_vars_configure_chirp() -> None:
    offenders: list[str] = []
    for path in _PRODUCTION_DOCS:
        text = path.read_text()
        offenders.extend(
            f"{path.relative_to(_ROOT)} contains {token}"
            for token in _UNSUPPORTED_CHIRP_ENV_VARS
            if token in text
        )

    assert not offenders


def test_production_docs_separate_chirp_and_pounce_preflight() -> None:
    for path in _PRODUCTION_DOCS:
        text = path.read_text()
        assert "chirp check myapp:app --deploy" in text
        assert "pounce check --app myapp:app" in text
        assert "pounce.toml" in text
        assert "not read by `app.run()` or `chirp run`" in text


def test_production_docs_do_not_claim_sse_compression() -> None:
    for path in _PRODUCTION_DOCS:
        text = path.read_text()
        assert "text/event-stream" in text
        assert "avoids compressing" in text


def test_production_docs_warn_introspection_bypasses_chirp_middleware() -> None:
    for path in _PRODUCTION_DOCS:
        text = path.read_text()
        compact = " ".join(text.split())
        assert "/_pounce/info" in text
        assert "disabled by default" in text
        assert "before Chirp middleware" in text
        assert "Do not expose it on a public internet interface" in compact


@pytest.mark.issue(565)
def test_apple_container_recipe_matches_verified_compatibility_boundary() -> None:
    paths = (
        *_PRODUCTION_DOCS,
        _ROOT / "examples" / "chirpui" / "lucky_cat" / "README.md",
    )
    required = (
        "Apple Container 1.1.0",
        "macOS 26.5.1",
        "linux/arm64/v8",
        "container system start",
        "container build",
        "--platform linux/arm64",
        "--publish 127.0.0.1:8000:8000",
        "--env CHIRP_HOST=0.0.0.0",
        "--env CHIRP_ENV=production",
        "--env CHIRP_SECRET_KEY",
        "container stop --signal SIGTERM --time 15",
        "not production sizing",
        "first-party Compose",
    )

    for path in paths:
        text = path.read_text()
        compact = " ".join(text.split())
        for token in required:
            assert token in text or token in compact, (
                f"{path.relative_to(_ROOT)} is missing {token}"
            )

    for path in _PRODUCTION_DOCS:
        text = path.read_text()
        for endpoint in ("/health", "/ready", "/", "/ft/stream"):
            assert endpoint in text, f"{path.relative_to(_ROOT)} is missing {endpoint}"
        assert "Docker/BuildKit and Railway" in text
