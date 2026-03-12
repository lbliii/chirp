"""Shared fixtures for chirp.server.negotiation tests."""

from pathlib import Path

import pytest
from kida import Environment, FileSystemLoader

from chirp.config import AppConfig
from chirp.templating.integration import create_environment

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


@pytest.fixture
def kida_env() -> Environment:
    return Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))


@pytest.fixture
def kida_env_with_packages() -> Environment:
    return create_environment(
        AppConfig(template_dir=TEMPLATES_DIR),
        filters={},
        globals_={},
    )
