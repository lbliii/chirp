"""Shared TestClient helpers for contract test modules.

Underscore-prefixed so pytest does not collect this file as a test module.
"""

from pathlib import Path

from chirp import App
from chirp.config import AppConfig

OOB_E2E_TEMPLATES = Path(__file__).parent / "templates" / "oob_e2e"


def _app(template_dir: Path = OOB_E2E_TEMPLATES, **overrides: object) -> App:
    """Build a chirp App wired to a template directory."""
    cfg = AppConfig(template_dir=template_dir, **overrides)
    return App(config=cfg)


_BOOSTED_HEADERS = {"HX-Request": "true", "HX-Boosted": "true"}


def _boosted_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Headers for an htmx-boosted (full-page) navigation request."""
    if extra is None:
        return dict(_BOOSTED_HEADERS)
    return {**_BOOSTED_HEADERS, **extra}
