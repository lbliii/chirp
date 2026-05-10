"""Guards for production deployment guidance."""

from pathlib import Path

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
        assert "chirp check myapp:app --warnings-as-errors" in text
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
